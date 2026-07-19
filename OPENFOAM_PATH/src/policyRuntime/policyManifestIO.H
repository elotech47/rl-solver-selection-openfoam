/**
 * @file policyManifestIO.H
 * Load OpenFOAM-dictionary policy_manifest into PolicyManifest.
 */

#ifndef policyManifestIO_H
#define policyManifestIO_H

#include "policyFeatures.H"
#include "IFstream.H"
#include "dictionary.H"
#include "error.H"

namespace ofRlChem
{

inline PolicyManifest loadPolicyManifest(const Foam::fileName& path)
{
    Foam::IFstream is(path);
    if (!is.good())
    {
        FatalErrorInFunction
            << "Cannot open policy manifest " << path
            << Foam::exit(Foam::FatalError);
    }
    Foam::dictionary dict(is);

    PolicyManifest m;
    m.obsDim = dict.getOrDefault<Foam::label>("obs_dim", 19);
    m.confidenceThreshold =
        dict.getOrDefault<Foam::scalar>("confidence_threshold", 0.6);
    m.numSteps = dict.getOrDefault<Foam::label>("num_steps", 20);
    m.modelPath = dict.getOrDefault<Foam::fileName>("torchScript", "policy.ts");

    if (dict.found("key_species"))
    {
        Foam::List<Foam::word> ks(dict.lookup("key_species"));
        m.keySpecies.clear();
        for (const auto& w : ks)
        {
            m.keySpecies.push_back(w);
        }
    }

    if (dict.found("obs_rms_mean"))
    {
        Foam::List<Foam::scalar> mean(dict.lookup("obs_rms_mean"));
        m.obsMean.assign(mean.begin(), mean.end());
    }
    if (dict.found("obs_rms_var"))
    {
        Foam::List<Foam::scalar> var(dict.lookup("obs_rms_var"));
        m.obsVar.assign(var.begin(), var.end());
    }

    if (static_cast<int>(m.obsMean.size()) != m.obsDim
     || static_cast<int>(m.obsVar.size()) != m.obsDim)
    {
        FatalErrorInFunction
            << "policy_manifest obs_rms size mismatch: mean="
            << m.obsMean.size() << " var=" << m.obsVar.size()
            << " obs_dim=" << m.obsDim
            << Foam::exit(Foam::FatalError);
    }
    return m;
}

} // namespace ofRlChem

#endif
