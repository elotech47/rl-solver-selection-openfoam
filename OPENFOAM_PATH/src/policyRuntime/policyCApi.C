/**
 * @file policyCApi.C
 * LibTorch JIT via:
 *   1) OFRL_POLICY_WORKER=path  — out-of-process (required on RHEL8/QB: Foam+ABI clash)
 *   2) else in-process TorchScript (Docker / matched ABI stacks)
 *
 * In-process uses -D_GLIBCXX_USE_CXX11_ABI=0 matching pip/pre-cxx11 LibTorch.
 */

#include "policyCApi.H"

#if __has_include(<torch/script.h>)
#   define OF_RL_HAS_TORCH 1
#   include <torch/script.h>
#   include <ATen/Context.h>
#else
#   define OF_RL_HAS_TORCH 0
#endif

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

struct OfRlPolicyHandle
{
    bool external{false};
    bool loaded{false};
    pid_t pid{-1};
    int to_worker{-1};   // write end
    int from_worker{-1}; // read end
#if OF_RL_HAS_TORCH
    torch::jit::script::Module module;
#endif
};

static bool writeAllFd(int fd, const void* buf, size_t n)
{
    const char* p = static_cast<const char*>(buf);
    while (n)
    {
        const ssize_t w = ::write(fd, p, n);
        if (w <= 0) return false;
        p += static_cast<size_t>(w);
        n -= static_cast<size_t>(w);
    }
    return true;
}

static bool readAllFd(int fd, void* buf, size_t n)
{
    char* p = static_cast<char*>(buf);
    while (n)
    {
        const ssize_t r = ::read(fd, p, n);
        if (r <= 0) return false;
        p += static_cast<size_t>(r);
        n -= static_cast<size_t>(r);
    }
    return true;
}

static OfRlPolicyHandle* loadExternal(const char* modelPath, const char* worker)
{
    int inPipe[2];  // parent writes → child stdin
    int outPipe[2]; // child stdout → parent reads
    if (pipe(inPipe) != 0 || pipe(outPipe) != 0)
    {
        std::perror("ofRlPolicy_load pipe");
        return nullptr;
    }

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, inPipe[0], STDIN_FILENO);
    posix_spawn_file_actions_adddup2(&actions, outPipe[1], STDOUT_FILENO);
    posix_spawn_file_actions_addclose(&actions, inPipe[0]);
    posix_spawn_file_actions_addclose(&actions, inPipe[1]);
    posix_spawn_file_actions_addclose(&actions, outPipe[0]);
    posix_spawn_file_actions_addclose(&actions, outPipe[1]);

    char* argv[] = {
        const_cast<char*>(worker),
        const_cast<char*>(modelPath),
        nullptr
    };

    // Child env without Foam traps (do not leave parent unset)
    const char* oldSig = std::getenv("FOAM_SIGFPE");
    const char* oldPre = std::getenv("LD_PRELOAD");
    const std::string sigSave = oldSig ? oldSig : "";
    const std::string preSave = oldPre ? oldPre : "";
    const bool hadSig = oldSig != nullptr;
    const bool hadPre = oldPre != nullptr;
    unsetenv("FOAM_SIGFPE");
    unsetenv("LD_PRELOAD");
    setenv("OMP_NUM_THREADS", "1", 1);
    setenv("MKL_NUM_THREADS", "1", 1);
    setenv("ATEN_NUM_THREADS", "1", 1);
    setenv("OPENBLAS_NUM_THREADS", "1", 1);
    setenv("TORCH_NUM_THREADS", "1", 1);

    pid_t pid = -1;
    // posix_spawn (not fork) — safe after MPI_Init
    const int rc = posix_spawn(&pid, worker, &actions, nullptr, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(inPipe[0]);
    close(outPipe[1]);

    if (hadSig) setenv("FOAM_SIGFPE", sigSave.c_str(), 1);
    else unsetenv("FOAM_SIGFPE");
    if (hadPre) setenv("LD_PRELOAD", preSave.c_str(), 1);
    else unsetenv("LD_PRELOAD");

    if (rc != 0)
    {
        std::fprintf(stderr, "ofRlPolicy_load posix_spawn: %s\n", std::strerror(rc));
        close(inPipe[1]);
        close(outPipe[0]);
        return nullptr;
    }

    auto* h = new OfRlPolicyHandle;
    h->external = true;
    h->pid = pid;
    h->to_worker = inPipe[1];
    h->from_worker = outPipe[0];

    char ready[8] = {};
    if (!readAllFd(h->from_worker, ready, 6) || std::strncmp(ready, "READY\n", 6) != 0)
    {
        std::fprintf
        (
            stderr,
            "ofRlPolicy_load: worker did not send READY (got '%.6s')\n",
            ready
        );
        ofRlPolicy_free(h);
        return nullptr;
    }
    h->loaded = true;
    std::fprintf
    (
        stderr,
        "ofRlPolicy_load: external worker pid=%d %s\n",
        static_cast<int>(pid),
        worker
    );
    return h;
}

extern "C" void* ofRlPolicy_load(const char* modelPath)
{
    if (!modelPath || !*modelPath) return nullptr;

    const char* worker = std::getenv("OFRL_POLICY_WORKER");
    if (worker && *worker)
    {
        return loadExternal(modelPath, worker);
    }

#if !OF_RL_HAS_TORCH
    std::fprintf(stderr, "ofRlPolicy_load: no Torch and no OFRL_POLICY_WORKER\n");
    return nullptr;
#else
    try
    {
        at::globalContext().setUserEnabledMkldnn(false);
        auto* h = new OfRlPolicyHandle;
        h->module = torch::jit::load(std::string(modelPath));
        h->module.eval();
        h->loaded = true;
        return h;
    }
    catch (const std::exception& e)
    {
        std::fprintf(stderr, "ofRlPolicy_load failed: %s\n", e.what());
        return nullptr;
    }
#endif
}

extern "C" void ofRlPolicy_free(void* handle)
{
    auto* h = static_cast<OfRlPolicyHandle*>(handle);
    if (!h) return;
    if (h->external)
    {
        if (h->to_worker >= 0)
        {
            const uint32_t quit = 0xFFFFFFFFu;
            writeAllFd(h->to_worker, &quit, sizeof(quit));
            close(h->to_worker);
        }
        if (h->from_worker >= 0) close(h->from_worker);
        if (h->pid > 0)
        {
            int status = 0;
            waitpid(h->pid, &status, 0);
        }
    }
    delete h;
}

extern "C" void ofRlPolicy_inferBatch
(
    void* handle,
    const double* feats,
    int n,
    double confidenceThreshold,
    int* flags,
    double* confidences,
    double* pQss
)
{
    if (!flags || !confidences || n <= 0) return;
    for (int i = 0; i < n; ++i)
    {
        flags[i] = 0;
        confidences[i] = 1.0;
        if (pQss) pQss[i] = 0.0;
    }

    auto* h = static_cast<OfRlPolicyHandle*>(handle);
    if (!h || !h->loaded || !feats) return;

    if (h->external)
    {
        const uint32_t nu = static_cast<uint32_t>(n);
        if (!writeAllFd(h->to_worker, &nu, sizeof(nu))) return;
        if (!writeAllFd(h->to_worker, &confidenceThreshold, sizeof(confidenceThreshold))) return;
        if (!writeAllFd(h->to_worker, feats, static_cast<size_t>(n) * 19u * sizeof(double))) return;

        for (int i = 0; i < n; ++i)
        {
            int32_t flag = 0;
            double conf = 0, pq = 0;
            if (!readAllFd(h->from_worker, &flag, sizeof(flag))) return;
            if (!readAllFd(h->from_worker, &conf, sizeof(conf))) return;
            if (!readAllFd(h->from_worker, &pq, sizeof(pq))) return;
            flags[i] = static_cast<int>(flag);
            confidences[i] = conf;
            if (pQss) pQss[i] = pq;
        }
        return;
    }

#if OF_RL_HAS_TORCH
    at::globalContext().setUserEnabledMkldnn(false);

    auto opts = torch::TensorOptions().dtype(torch::kFloat32);
    torch::Tensor x = torch::zeros({static_cast<long>(n), 19}, opts);
    auto a = x.accessor<float, 2>();
    for (int i = 0; i < n; ++i)
    {
        for (int j = 0; j < 19; ++j)
        {
            a[i][j] = static_cast<float>(feats[i * 19 + j]);
        }
    }

    std::vector<torch::jit::IValue> inputs;
    inputs.push_back(x);
    torch::Tensor logits = h->module.forward(inputs).toTensor();
    torch::Tensor probs = torch::softmax(logits, /*dim=*/1);
    auto p = probs.accessor<float, 2>();
    for (int i = 0; i < n; ++i)
    {
        const double p0 = p[i][0];
        const double p1 = p[i][1];
        if (pQss) pQss[i] = p1;
        const int argmax = (p1 > p0) ? 1 : 0;
        const double conf = (argmax == 1) ? p1 : p0;
        confidences[i] = conf;
        flags[i] = (conf < confidenceThreshold) ? 0 : argmax;
    }
#else
    (void)confidenceThreshold;
#endif
}
