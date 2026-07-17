/*---------------------------------------------------------------------------*\
  rlChemistryModel implementation
\*---------------------------------------------------------------------------*/

#include "rlChemistryModel.H"
#include "policyRuntime.H"
#include <chrono>

template<class ReactionThermo, class ThermoType>
Foam::rlChemistryModel<ReactionThermo, ThermoType>::rlChemistryModel
(
    ReactionThermo& thermo
)
:
    StandardChemistryModel<ReactionThermo, ThermoType>(thermo),
    mode_(Mode::rlAdaptive),
    maxChemDeltaT_(1e-6),
    numSteps_(20),
    confidenceThreshold_(0.6),
    policyManifestPath_("policy_manifest.json"),
    policyTorchPath_("policy.pt"),
    solverFlag_
    (
        IOobject
        (
            "solverFlag",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("solverFlag", dimless, 0)
    ),
    chemCpuTime_
    (
        IOobject
        (
            "chemCpuTime",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("chemCpuTime", dimTime, 0)
    ),
    Tconsistency_
    (
        IOobject
        (
            "Tconsistency",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("Tconsistency", dimTemperature, 0)
    ),
    Tprev_(this->mesh().nCells(), 0),
    stepsSinceDecision_(this->mesh().nCells(), 0),
    lastDecision_(this->mesh().nCells(), 0)
{
    const dictionary& dict = this->subDict("rl");
    const word modeName = dict.getOrDefault<word>("mode", "rlAdaptive");
    if (modeName == "cvodeOnly") mode_ = Mode::cvodeOnly;
    else if (modeName == "qssOnly") mode_ = Mode::qssOnly;
    else mode_ = Mode::rlAdaptive;

    maxChemDeltaT_ = dict.getOrDefault<scalar>("maxChemDeltaT", 1e-6);
    numSteps_ = dict.getOrDefault<label>("numSteps", 20);
    confidenceThreshold_ = dict.getOrDefault<scalar>("confidenceThreshold", 0.6);
    policyManifestPath_ = dict.getOrDefault<word>("manifest", "policy_manifest.json");
    policyTorchPath_ = dict.getOrDefault<word>("torchScript", "policy.ts");
}


template<class ReactionThermo, class ThermoType>
Foam::rlChemistryModel<ReactionThermo, ThermoType>::~rlChemistryModel()
{}


template<class ReactionThermo, class ThermoType>
Foam::scalar Foam::rlChemistryModel<ReactionThermo, ThermoType>::solve
(
    const scalar deltaT
)
{
    // Sub-step into chemistry windows ≤ maxChemDeltaT_
    scalar tDone = 0.0;
    scalar dtChem = min(deltaT, maxChemDeltaT_);
    label nSub = max(label(1), label(ceil(deltaT/maxChemDeltaT_)));
    dtChem = deltaT/nSub;

    // Load policy once (cached static)
    static bool policyInit = false;
    static ofRlChem::PolicyManifest manifest;
    static std::unique_ptr<ofRlChem::PolicyRuntime> policy;
    if (!policyInit && mode_ == Mode::rlAdaptive)
    {
        manifest.confidenceThreshold = confidenceThreshold_;
        manifest.numSteps = numSteps_;
        manifest.modelPath = policyTorchPath_;
        // obs_rms filled by export script into companion vectors; for now empty → identity-ish
        policy.reset(new ofRlChem::PolicyRuntime(manifest));
        policyInit = true;
    }

    const label nCells = this->mesh().nCells();
    // Key species indices resolved once from thermo composition names
    // (OH, H2O, O2, H2, H2O2, O, H, N2)
    // Full name lookup left to case thermo; here we document the contract.

    for (label s = 0; s < nSub; ++s)
    {
        // Gather features & refresh decisions every numSteps_ windows
        std::vector<std::array<double, 19>> feats;
        std::vector<label> activeCells;
        if (mode_ == Mode::rlAdaptive)
        {
            feats.reserve(nCells);
            for (label celli = 0; celli < nCells; ++celli)
            {
                stepsSinceDecision_[celli] += 1;
                if
                (
                    stepsSinceDecision_[celli] >= numSteps_
                    || s == 0
                )
                {
                    activeCells.push_back(celli);
                    stepsSinceDecision_[celli] = 0;
                }
            }
            // Build observations for active cells (Ykey extraction omitted —
            // filled via specie composition fields in production wiring).
            feats.resize(activeCells.size());
            for (size_t k = 0; k < activeCells.size(); ++k)
            {
                const label celli = activeCells[k];
                double Ykey[8] = {};
                double Yprev[8] = {};
                const bool hasPrev = (Tprev_[celli] > SMALL);
                feats[k] = ofRlChem::normalizeObs
                (
                    ofRlChem::buildObservation19
                    (
                        this->thermo().T()[celli],
                        this->thermo().p()[celli],
                        Ykey,
                        Tprev_[celli],
                        Yprev,
                        hasPrev
                    ),
                    policy->manifest()
                );
            }
            std::vector<int> flags;
            std::vector<double> conf;
            if (policy)
            {
                policy->inferBatch(feats, flags, conf);
                for (size_t k = 0; k < activeCells.size(); ++k)
                {
                    lastDecision_[activeCells[k]] = flags[k];
                    solverFlag_[activeCells[k]] = flags[k];
                }
            }
        }
        else if (mode_ == Mode::cvodeOnly)
        {
            forAll(solverFlag_, celli) solverFlag_[celli] = 0;
        }
        else
        {
            forAll(solverFlag_, celli) solverFlag_[celli] = 1;
        }

        // Per-cell chemistry (delegates to StandardChemistryModel solve path
        // with the selected solver — production code swaps chemistrySolver
        // per cell via qss/cvode instances).
        const auto t0 = std::chrono::steady_clock::now();

        // Call parent cell loop; selected solver applied inside solveCell override
        // when fully wired. For now: use StandardChemistryModel::solve.
        // Note: per-cell dispatch requires solve chemistrySolver selection —
        // documented as next wiring step after library load.
        (void)StandardChemistryModel<ReactionThermo, ThermoType>::solve(dtChem);

        const auto t1 = std::chrono::steady_clock::now();
        const double wall =
            std::chrono::duration<double>(t1 - t0).count();
        forAll(chemCpuTime_, celli)
        {
            chemCpuTime_[celli] = wall/nCells; // equal split until per-cell timers
        }

        // Update history buffers
        for (label celli = 0; celli < nCells; ++celli)
        {
            Tprev_[celli] = this->thermo().T()[celli];
        }

        tDone += dtChem;
    }

    return dtChem; // characteristic chemistry deltaT
}

// ************************************************************************* //
