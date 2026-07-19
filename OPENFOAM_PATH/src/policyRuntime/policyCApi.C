/**
 * @file policyCApi.C
 * LibTorch JIT — compile with -D_GLIBCXX_USE_CXX11_ABI=0 (pip wheel).
 */

#include "policyCApi.H"

#if __has_include(<torch/script.h>)
#   define OF_RL_HAS_TORCH 1
#   include <torch/script.h>
#   include <ATen/Context.h>
#else
#   define OF_RL_HAS_TORCH 0
#endif

#include <cstdio>
#include <string>
#include <vector>

struct OfRlPolicyHandle
{
#if OF_RL_HAS_TORCH
    torch::jit::script::Module module;
#endif
    bool loaded{false};
};

extern "C" void* ofRlPolicy_load(const char* modelPath)
{
#if !OF_RL_HAS_TORCH
    (void)modelPath;
    return nullptr;
#else
    if (!modelPath || !*modelPath) return nullptr;
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
    delete static_cast<OfRlPolicyHandle*>(handle);
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
#if OF_RL_HAS_TORCH
    auto* h = static_cast<OfRlPolicyHandle*>(handle);
    if (!h || !h->loaded || !feats) return;

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
    (void)handle;
    (void)feats;
    (void)confidenceThreshold;
    (void)pQss;
#endif
}
