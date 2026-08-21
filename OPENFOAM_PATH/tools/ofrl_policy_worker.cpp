/**
 * @file ofrl_policy_worker.cpp
 * Standalone TorchScript worker (ABI=0 LibTorch). Never linked into OpenFOAM —
 * Foam's operator new + ABI mismatch aborts in-process jit::load on RHEL8.
 *
 * Protocol (stdin/stdout, native endian):
 *   after load: writes "READY\n"
 *   request:  uint32 n, float64 thresh, then n*19 float64 features (row-major)
 *   reply:    n times { int32 flag, float64 conf, float64 pQss }
 *   quit:     uint32 n == 0xFFFFFFFFu
 */
#include <torch/script.h>
#include <ATen/Context.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

static bool writeAll(const void* buf, size_t n)
{
    const char* p = static_cast<const char*>(buf);
    while (n)
    {
        const size_t w = std::fwrite(p, 1, n, stdout);
        if (w == 0) return false;
        p += w;
        n -= w;
    }
    return true;
}

static bool readAll(void* buf, size_t n)
{
    char* p = static_cast<char*>(buf);
    while (n)
    {
        const size_t r = std::fread(p, 1, n, stdin);
        if (r == 0) return false;
        p += r;
        n -= r;
    }
    return true;
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: ofrl_policy_worker policy.ts\n");
        return 2;
    }

    at::globalContext().setUserEnabledMkldnn(false);
    // Single-thread: do not steal cores from Foam MPI ranks
    setenv("OMP_NUM_THREADS", "1", 1);
    setenv("MKL_NUM_THREADS", "1", 1);
    setenv("ATEN_NUM_THREADS", "1", 1);
    setenv("OPENBLAS_NUM_THREADS", "1", 1);
    setenv("TORCH_NUM_THREADS", "1", 1);

    try
    {
        auto module = torch::jit::load(argv[1]);
        module.eval();
        std::fputs("READY\n", stdout);
        std::fflush(stdout);

        for (;;)
        {
            uint32_t n = 0;
            if (!readAll(&n, sizeof(n))) break;
            if (n == 0xFFFFFFFFu) break;

            double thresh = 0.6;
            if (!readAll(&thresh, sizeof(thresh))) break;

            std::vector<double> feats(static_cast<size_t>(n) * 19u);
            if (!readAll(feats.data(), feats.size() * sizeof(double))) break;

            at::globalContext().setUserEnabledMkldnn(false);
            auto opts = torch::TensorOptions().dtype(torch::kFloat32);
            torch::Tensor x = torch::zeros({static_cast<long>(n), 19}, opts);
            auto a = x.accessor<float, 2>();
            for (uint32_t i = 0; i < n; ++i)
            {
                for (int j = 0; j < 19; ++j)
                {
                    a[i][j] = static_cast<float>(feats[i * 19u + static_cast<uint32_t>(j)]);
                }
            }

            std::vector<torch::jit::IValue> inputs;
            inputs.push_back(x);
            torch::Tensor logits = module.forward(inputs).toTensor();
            torch::Tensor probs = torch::softmax(logits, /*dim=*/1);
            auto p = probs.accessor<float, 2>();

            for (uint32_t i = 0; i < n; ++i)
            {
                const double p0 = p[i][0];
                const double p1 = p[i][1];
                const int argmax = (p1 > p0) ? 1 : 0;
                const double conf = (argmax == 1) ? p1 : p0;
                const int32_t flag = (conf < thresh) ? 0 : argmax;
                if (!writeAll(&flag, sizeof(flag))) return 1;
                if (!writeAll(&conf, sizeof(conf))) return 1;
                if (!writeAll(&p1, sizeof(p1))) return 1;
            }
            std::fflush(stdout);
        }
    }
    catch (const std::exception& e)
    {
        std::fprintf(stderr, "ofrl_policy_worker failed: %s\n", e.what());
        return 1;
    }
    return 0;
}
