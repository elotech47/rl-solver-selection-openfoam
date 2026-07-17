/**
 * @file policyRuntime.H
 * Batched RL policy inference + 19-D feature builder (handoff parity).
 */

#ifndef policyRuntime_H
#define policyRuntime_H

#include <string>
#include <vector>
#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>

// Optional LibTorch
#if __has_include(<torch/script.h>)
#   define OF_RL_HAS_TORCH 1
#   include <torch/script.h>
#   include <torch/torch.h>
#else
#   define OF_RL_HAS_TORCH 0
#endif

namespace ofRlChem
{

struct PolicyManifest
{
    int obsDim{19};
    double confidenceThreshold{0.6};
    int numSteps{20};
    std::vector<std::string> keySpecies
    {
        "OH", "H2O", "O2", "H2", "H2O2", "O", "H", "N2"
    };
    std::vector<double> obsMean;
    std::vector<double> obsVar;
    std::string modelPath;
};

/** Build raw 19-D observation (before obs_rms), matching handoff ObservationBuilder. */
inline std::array<double, 19> buildObservation19
(
    double T,
    double P,                 // Pa
    const double* Ykey,       // length 8, order in manifest
    double T_prev,
    const double* Ykey_prev,
    bool hasPrev
)
{
    constexpr double oneAtm = 101325.0;
    std::array<double, 19> obs{};
    const double T_norm = (T - 300.0) / 2000.0;
    obs[0] = T_norm;
    for (int i = 0; i < 8; ++i)
    {
        obs[1 + i] = std::log10(std::max(std::abs(Ykey[i]), 1e-20));
    }
    obs[9] = std::log10(P / oneAtm);

    if (hasPrev)
    {
        obs[10] = std::log10(T) - std::log10(std::max(T_prev, 1e-30));
        for (int i = 0; i < 8; ++i)
        {
            const double yi = std::log10(std::max(std::abs(Ykey[i]), 1e-20));
            const double yip =
                std::log10(std::max(std::abs(Ykey_prev[i]), 1e-20));
            obs[11 + i] = yi - yip;
        }
    }
    // else: gradients stay 0 (first query)
    return obs;
}

inline std::array<double, 19> normalizeObs
(
    const std::array<double, 19>& raw,
    const PolicyManifest& m
)
{
    std::array<double, 19> out{};
    for (int i = 0; i < 19; ++i)
    {
        const double mean = (i < (int)m.obsMean.size()) ? m.obsMean[i] : 0.0;
        const double var = (i < (int)m.obsVar.size()) ? m.obsVar[i] : 1.0;
        double z = (raw[i] - mean) / (std::sqrt(var) + 1e-8);
        if (z > 10.0) z = 10.0;
        if (z < -10.0) z = -10.0;
        out[i] = z;
    }
    return out;
}

/**
 * Action: 0 = CVODE, 1 = QSS.
 * deterministic argmax; if confidence < threshold → force CVODE (0).
 */
class PolicyRuntime
{
public:
    explicit PolicyRuntime(const PolicyManifest& manifest)
    :
        manifest_(manifest)
    {
#if OF_RL_HAS_TORCH
        if (!manifest_.modelPath.empty())
        {
            module_ = torch::jit::load(manifest_.modelPath);
            module_.eval();
            loaded_ = true;
        }
#endif
    }

    /** Batch infer: features [nCells x 19] → solverFlag per cell (0/1). */
    void inferBatch
    (
        const std::vector<std::array<double, 19>>& features,
        std::vector<int>& solverFlags,
        std::vector<double>& confidences
    ) const
    {
        const size_t n = features.size();
        solverFlags.assign(n, 0);
        confidences.assign(n, 1.0);

#if OF_RL_HAS_TORCH
        if (!loaded_ || n == 0) return;

        auto opts = torch::TensorOptions().dtype(torch::kFloat32);
        torch::Tensor x = torch::zeros({(long)n, 19}, opts);
        auto a = x.accessor<float, 2>();
        for (size_t i = 0; i < n; ++i)
        {
            for (int j = 0; j < 19; ++j) a[i][j] = static_cast<float>(features[i][j]);
        }

        std::vector<torch::jit::IValue> inputs;
        inputs.push_back(x);
        // Expect actor logits [n, 2]
        torch::Tensor logits = module_.forward(inputs).toTensor();
        torch::Tensor probs = torch::softmax(logits, /*dim=*/1);
        auto p = probs.accessor<float, 2>();
        for (size_t i = 0; i < n; ++i)
        {
            const int argmax = (p[i][1] > p[i][0]) ? 1 : 0;
            const double conf = p[i][argmax];
            confidences[i] = conf;
            solverFlags[i] =
                (conf < manifest_.confidenceThreshold) ? 0 : argmax;
        }
#else
        (void)manifest_;
        // Without LibTorch: default all to CVODE (safe)
#endif
    }

    const PolicyManifest& manifest() const { return manifest_; }

private:
    PolicyManifest manifest_;
#if OF_RL_HAS_TORCH
    mutable torch::jit::script::Module module_;
    bool loaded_{false};
#endif
};

} // namespace ofRlChem

#endif
