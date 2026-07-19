/**
 * @file policyRuntime.H
 * Batched RL policy inference (LibTorch via C ABI — no torch headers).
 */

#ifndef policyRuntime_H
#define policyRuntime_H

#include "policyFeatures.H"
#include "policyCApi.H"
#include <stdexcept>

namespace ofRlChem
{

/**
 * Action: 0 = CVODE, 1 = QSS.
 * deterministic argmax; if confidence < threshold → force CVODE (0).
 */
class PolicyRuntime
{
public:
    explicit PolicyRuntime(const PolicyManifest& manifest)
    :
        manifest_(manifest),
        handle_(ofRlPolicy_load(manifest.modelPath.c_str()))
    {
        if (!handle_)
        {
            throw std::runtime_error(
                "ofRlPolicy_load failed for " + manifest.modelPath
            );
        }
    }

    ~PolicyRuntime()
    {
        ofRlPolicy_free(handle_);
        handle_ = nullptr;
    }

    PolicyRuntime(const PolicyRuntime&) = delete;
    PolicyRuntime& operator=(const PolicyRuntime&) = delete;

    void inferBatch
    (
        const std::vector<std::array<double, 19>>& features,
        std::vector<int>& solverFlags,
        std::vector<double>& confidences,
        std::vector<double>& pQss
    ) const
    {
        const int n = static_cast<int>(features.size());
        solverFlags.assign(static_cast<size_t>(n), 0);
        confidences.assign(static_cast<size_t>(n), 1.0);
        pQss.assign(static_cast<size_t>(n), 0.0);
        if (n == 0) return;

        std::vector<double> flat(static_cast<size_t>(n) * 19);
        for (int i = 0; i < n; ++i)
        {
            for (int j = 0; j < 19; ++j)
            {
                flat[static_cast<size_t>(i * 19 + j)] =
                    features[static_cast<size_t>(i)][j];
            }
        }
        ofRlPolicy_inferBatch
        (
            handle_,
            flat.data(),
            n,
            manifest_.confidenceThreshold,
            solverFlags.data(),
            confidences.data(),
            pQss.data()
        );
    }

    /** Convenience overload without pQss. */
    void inferBatch
    (
        const std::vector<std::array<double, 19>>& features,
        std::vector<int>& solverFlags,
        std::vector<double>& confidences
    ) const
    {
        std::vector<double> pQss;
        inferBatch(features, solverFlags, confidences, pQss);
    }

    const PolicyManifest& manifest() const { return manifest_; }
    bool loaded() const { return handle_ != nullptr; }

private:
    PolicyManifest manifest_;
    void* handle_{nullptr};
};

} // namespace ofRlChem

#endif
