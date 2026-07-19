/**
 * @file policyFeatures.H
 * 19-D observation builder + PolicyManifest (no LibTorch).
 */

#ifndef policyFeatures_H
#define policyFeatures_H

#include <string>
#include <vector>
#include <array>
#include <cmath>

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
        const double mean =
            (i < static_cast<int>(m.obsMean.size())) ? m.obsMean[i] : 0.0;
        const double var =
            (i < static_cast<int>(m.obsVar.size())) ? m.obsVar[i] : 1.0;
        double z = (raw[i] - mean) / (std::sqrt(var) + 1e-8);
        if (z > 10.0) z = 10.0;
        if (z < -10.0) z = -10.0;
        out[i] = z;
    }
    return out;
}

} // namespace ofRlChem

#endif
