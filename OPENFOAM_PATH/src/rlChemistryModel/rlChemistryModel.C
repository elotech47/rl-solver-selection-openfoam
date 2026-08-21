/*---------------------------------------------------------------------------*\
  rlChemistryModel implementation — features → policy → QSS/CVODE dispatch

  E16.5: decision/feature clock is physical chemistry time
    τ_dec = numSteps × dtRef
  not CFD micro-window count. Δlog features span consecutive τ_dec snapshots.
\*---------------------------------------------------------------------------*/

#include "rlChemistryModel.H"
#include "policyRuntime.H"
#include "policyManifestIO.H"
#include "UniformField.H"
#include "OFstream.H"
#include "Pstream.H"
#include <chrono>
#include <cctype>

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

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
    dtRef_(1e-6),
    tauDec_(2e-5),
    confidenceThreshold_(0.6),
    policyManifestPath_("policy_manifest"),
    policyTorchPath_("policy.ts"),
    policyFlag_
    (
        IOobject
        (
            "policyFlag",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("policyFlag", dimless, 0)
    ),
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
    qssFallbackCount_
    (
        IOobject
        (
            "qssFallbackCount",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("qssFallbackCount", dimless, 0)
    ),
    yClipMass_
    (
        IOobject
        (
            "yClipMass",
            this->mesh().time().timeName(),
            this->mesh(),
            IOobject::NO_READ,
            IOobject::AUTO_WRITE
        ),
        this->mesh(),
        dimensionedScalar("yClipMass", dimless, 0)
    ),
    Tprev_(this->mesh().nCells(), 0),
    YkeyPrev_(this->mesh().nCells()),
    hasSnapPrev_(this->mesh().nCells(), false),
    timeSinceDecision_(this->mesh().nCells(), 0),
    nDecisionsTaken_(this->mesh().nCells(), 0),
    lastDecision_(this->mesh().nCells(), 0),
    forceCvodeHold_(this->mesh().nCells(), false),
    everDecided_(this->mesh().nCells(), false),
    logUsage_(true),
    logDecisions_(false),
    logFallbackReasons_(true),
    chemTimeAccum_(0),
    warnedOversizedDt_(false),
    policyWallAcc_(0),
    testDeltaTIndex_(0),
    keysResolved_(false),
    cvodeUdStorage_(nullptr)
{
    cvodeUdStorage_ = new ofRlChem::CvodeUD
        <rlChemistryModel<ReactionThermo, ThermoType>>();
    const dictionary& dict = this->subDict("rl");
    const word modeName = dict.getOrDefault<word>("mode", "rlAdaptive");
    if (modeName == "cvodeOnly") mode_ = Mode::cvodeOnly;
    else if (modeName == "qssOnly") mode_ = Mode::qssOnly;
    else mode_ = Mode::rlAdaptive;

    maxChemDeltaT_ = dict.getOrDefault<scalar>("maxChemDeltaT", 1e-6);
    numSteps_ = dict.getOrDefault<label>("numSteps", 20);
    // dtRef: dict override → else filled from manifest in ensurePolicy
    // Fallback maxChemDeltaT keeps E16.4 case scripts working before manifest load
    dtRef_ = dict.getOrDefault<scalar>("dtRef", -1);
    confidenceThreshold_ = dict.getOrDefault<scalar>("confidenceThreshold", 0.6);
    policyManifestPath_ = dict.getOrDefault<fileName>("manifest", "policy_manifest");
    policyTorchPath_ = dict.getOrDefault<fileName>("torchScript", "policy.ts");
    logUsage_ = dict.getOrDefault<Switch>("logUsage", true);
    logDecisions_ = dict.getOrDefault<Switch>("logDecisions", false);
    logFallbackReasons_ = dict.getOrDefault<Switch>("logFallbackReasons", true);

    if (dict.found("testDeltaTSchedule"))
    {
        dict.lookup("testDeltaTSchedule") >> testDeltaTSchedule_;
        Info<< "rlChemistryModel: testDeltaTSchedule ("
            << testDeltaTSchedule_.size() << " entries) — E16.5 clock test hook"
            << endl;
    }

    if (this->found("qssCoeffs"))
    {
        const dictionary& q = this->subDict("qssCoeffs");
        qssCoeffs_.epsmin = q.getOrDefault<scalar>("epsmin", 0.02);
        qssCoeffs_.epsmax = q.getOrDefault<scalar>("epsmax", 100);
        qssCoeffs_.dtmin = q.getOrDefault<scalar>("dtmin", 1e-12);
        qssCoeffs_.dtmax = q.getOrDefault<scalar>("dtmax", 1e-6);
        qssCoeffs_.abstol = q.getOrDefault<scalar>("abstol", 1e-11);
        qssCoeffs_.itermax = q.getOrDefault<label>("itermax", 2);
        qssCoeffs_.Tfreeze = q.getOrDefault<Switch>("Tfreeze", true);
    }
    if (this->found("cvodeCoeffs"))
    {
        const dictionary& c = this->subDict("cvodeCoeffs");
        cvodeCoeffs_.rtol = c.getOrDefault<scalar>("relTol", 1e-8);
        cvodeCoeffs_.atol = c.getOrDefault<scalar>("absTol", 1e-12);
        cvodeCoeffs_.mxsteps = c.getOrDefault<label>("maxSteps", 100000);
    }
    if (this->found("guardCoeffs"))
    {
        const dictionary& g = this->subDict("guardCoeffs");
        guardCoeffs_.enabled = g.getOrDefault<Switch>("enabled", true);
        guardCoeffs_.epsY = g.getOrDefault<scalar>("epsY", 1e-8);
        guardCoeffs_.epsSumY = g.getOrDefault<scalar>("epsSumY", 1e-2);
        guardCoeffs_.dTmaxWindow = g.getOrDefault<scalar>("dTmaxWindow", 500);
        guardCoeffs_.TminAccept = g.getOrDefault<scalar>("TminAccept", 310);
        guardCoeffs_.TmaxAccept = g.getOrDefault<scalar>("TmaxAccept", 3400);
    }
    // CFD modes always use guards when method=rl (E17.2). Disable only via
    // guardCoeffs.enabled false (0D diagnostics / ablation).
    Info<< "rlChemistryModel: guards "
        << (guardCoeffs_.enabled ? "ON" : "OFF")
        << " epsY=" << guardCoeffs_.epsY
        << " epsSumY=" << guardCoeffs_.epsSumY
        << " dTmaxWindow=" << guardCoeffs_.dTmaxWindow
        << " Taccept=[" << guardCoeffs_.TminAccept
        << "," << guardCoeffs_.TmaxAccept << "]"
        << endl;

    forAll(YkeyPrev_, celli)
    {
        YkeyPrev_[celli] = Zero;
    }

    // Provisional τ_dec until manifest load (dict dtRef or maxChemDeltaT)
    if (dtRef_ < 0)
    {
        dtRef_ = maxChemDeltaT_;
    }
    tauDec_ = scalar(numSteps_)*dtRef_;
}


template<class ReactionThermo, class ThermoType>
Foam::rlChemistryModel<ReactionThermo, ThermoType>::~rlChemistryModel()
{
    delete static_cast
        <ofRlChem::CvodeUD<rlChemistryModel<ReactionThermo, ThermoType>>*>
        (cvodeUdStorage_);
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

template<class ReactionThermo, class ThermoType>
void Foam::rlChemistryModel<ReactionThermo, ThermoType>::resolveKeySpecies() const
{
    if (keysResolved_) return;

    std::vector<std::string> names =
    {
        "oh", "h2o", "o2", "h2", "h2o2", "o", "h", "n2"
    };
    if (policy_ && !policy_->manifest().keySpecies.empty())
    {
        names = policy_->manifest().keySpecies;
    }

    keyIndices_.setSize(8, -1);
    const PtrList<volScalarField>& Y = this->Y_;
    for (label k = 0; k < 8; ++k)
    {
        std::string want = names[static_cast<size_t>(k)];
        for (char& ch : want)
        {
            ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
        }
        forAll(Y, i)
        {
            word nm = Y[i].name();
            std::string have = nm;
            for (char& ch : have)
            {
                ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
            }
            if (have == want)
            {
                keyIndices_[k] = i;
                break;
            }
        }
        if (keyIndices_[k] < 0)
        {
            FatalErrorInFunction
                << "Cannot resolve key species '" << want
                << "' in composition Y fields"
                << exit(FatalError);
        }
    }
    keysResolved_ = true;
    Info<< "rlChemistryModel: key species indices = " << keyIndices_ << endl;
}


template<class ReactionThermo, class ThermoType>
void Foam::rlChemistryModel<ReactionThermo, ThermoType>::ensurePolicy() const
{
    if (policy_ || mode_ != Mode::rlAdaptive) return;

    fileName manPath = policyManifestPath_;
    if (!isFile(manPath))
    {
        const fileName alt =
            getEnv("WM_PROJECT_USER_DIR")/"policy"/policyManifestPath_;
        if (isFile(alt)) manPath = alt;
    }
    Info<< "rlChemistryModel: loading manifest " << manPath << endl;
    ofRlChem::PolicyManifest man = ofRlChem::loadPolicyManifest(manPath);
    man.confidenceThreshold = confidenceThreshold_;
    man.numSteps = numSteps_;

    // Resolve dtRef / τ_dec: explicit rl.dtRef > manifest dt_ref > maxChemDeltaT
    const dictionary& dict = this->subDict("rl");
    if (dict.found("dtRef"))
    {
        dtRef_ = dict.get<scalar>("dtRef");
    }
    else if (man.dtRef > 0)
    {
        dtRef_ = man.dtRef;
    }
    else
    {
        dtRef_ = maxChemDeltaT_;
    }
    man.dtRef = dtRef_;
    tauDec_ = scalar(numSteps_)*dtRef_;
    Info<< "rlChemistryModel: dtRef=" << dtRef_
        << " numSteps=" << numSteps_
        << " tauDec=" << tauDec_ << endl;

    fileName tsPath = policyTorchPath_;
    if (!isFile(tsPath))
    {
        const fileName alt =
            getEnv("WM_PROJECT_USER_DIR")/"policy"/policyTorchPath_;
        if (isFile(alt)) tsPath = alt;
        else if (isFile(manPath.path()/policyTorchPath_))
        {
            tsPath = manPath.path()/policyTorchPath_;
        }
    }
    man.modelPath = tsPath;
    Info<< "rlChemistryModel: loading TorchScript " << tsPath << endl;
    policy_.reset(new ofRlChem::PolicyRuntime(man));
    Info<< "rlChemistryModel: loaded policy " << tsPath
        << " manifest " << manPath << endl;
}


template<class ReactionThermo, class ThermoType>
Foam::scalar Foam::rlChemistryModel<ReactionThermo, ThermoType>::solve
(
    const scalar deltaTIn
)
{
    this->correct();

    if (!this->chemistry_)
    {
        return GREAT;
    }

    ensurePolicy();
    resolveKeySpecies();

    scalar deltaT = deltaTIn;
    if (testDeltaTSchedule_.size())
    {
        deltaT =
            testDeltaTSchedule_
            [
                testDeltaTIndex_ % testDeltaTSchedule_.size()
            ];
        ++testDeltaTIndex_;
    }

    const label nSub = max(label(1), label(ceil(deltaT/maxChemDeltaT_)));
    const scalar dtChem = deltaT/nSub;
    const label nCells = this->mesh().nCells();
    const label nSpecie = this->nSpecie_;
    policyWallAcc_ = 0;

    // CFD / chemistry window larger than one decision interval: decide every
    // window and let Δlog span the actual elapsed chemistry time.
    const bool oversizedWindow = (dtChem > tauDec_ + SMALL);
    if (oversizedWindow && !warnedOversizedDt_)
    {
        WarningInFunction
            << "chemistry window dtChem=" << dtChem
            << " > tauDec=" << tauDec_
            << " (numSteps×dtRef). Deciding every window; Δlog spans "
            << "actual elapsed chemistry time (not a fixed τ_dec)."
            << endl;
        warnedOversizedDt_ = true;
    }

    scalar deltaTMin = GREAT;

    tmp<volScalarField> trho0(this->thermo().rho());
    const scalarField& rho0 = trho0();
    const scalarField& T0field = this->thermo().T();
    const scalarField& p0field = this->thermo().p();

    List<scalarField> cWork(nCells);
    scalarField Twork(nCells);
    scalarField pWork(nCells);
    List<scalarField> cInit(nCells);

    // Per-CFD-step usage (summed over chemistry sub-windows)
    scalarField cpuThisSolve(nCells, 0);
    boolList fellBackThisSolve(nCells, false);
    // Layer-2 reject reason tallies (first failing check; cell counted once)
    label nFbYneg = 0;
    label nFbSumY = 0;
    label nFbDT = 0;
    label nFbTbounds = 0;
    label nFbInteg = 0;
    scalar maxNegY = 0;      // max of (-minY) among Y_negative rejects
    scalar maxSumDrift = 0;  // max |ΣY−1| among sumY_drift rejects

    for (label celli = 0; celli < nCells; ++celli)
    {
        cWork[celli].setSize(nSpecie);
        cInit[celli].setSize(nSpecie);
        const scalar rhoi = rho0[celli];
        for (label i = 0; i < nSpecie; ++i)
        {
            cInit[celli][i] =
                rhoi*this->Y_[i][celli]/this->specieThermo_[i].W();
            cWork[celli][i] = cInit[celli][i];
        }
        Twork[celli] = T0field[celli];
        pWork[celli] = p0field[celli];
    }

    for (label s = 0; s < nSub; ++s)
    {
        if (mode_ == Mode::rlAdaptive)
        {
            std::vector<label> active;
            for (label celli = 0; celli < nCells; ++celli)
            {
                // Absolute τ_dec grid: due when chemTimeAccum >= n·τ_dec
                const scalar nextDue =
                    scalar(nDecisionsTaken_[celli])*tauDec_;
                const bool due =
                    oversizedWindow
                 || (chemTimeAccum_ + SMALL >= nextDue);
                if (due)
                {
                    active.push_back(celli);
                }
            }

            std::vector<std::array<double, 19>> feats(active.size());
            for (size_t k = 0; k < active.size(); ++k)
            {
                const label celli = active[k];
                double Ykey[8];
                double Yprev[8];
                scalar rhoNow = 0;
                for (label i = 0; i < nSpecie; ++i)
                {
                    rhoNow += cWork[celli][i]*this->specieThermo_[i].W();
                }
                rhoNow = max(rhoNow, SMALL);
                for (label j = 0; j < 8; ++j)
                {
                    const label si = keyIndices_[j];
                    Ykey[j] = cWork[celli][si]*this->specieThermo_[si].W()/rhoNow;
                    Yprev[j] = YkeyPrev_[celli][j];
                }
                const bool hasPrev = hasSnapPrev_[celli];
                feats[k] = ofRlChem::normalizeObs
                (
                    ofRlChem::buildObservation19
                    (
                        Twork[celli],
                        pWork[celli],
                        Ykey,
                        Tprev_[celli],
                        Yprev,
                        hasPrev
                    ),
                    policy_->manifest()
                );
            }

            std::vector<int> flags;
            std::vector<double> conf;
            std::vector<double> pQss;
            {
                const auto t0 = std::chrono::steady_clock::now();
                policy_->inferBatch(feats, flags, conf, pQss);
                policyWallAcc_ +=
                    std::chrono::duration<double>
                    (
                        std::chrono::steady_clock::now() - t0
                    ).count();
            }

            {
                if (logDecisions_)
                {
                    const fileName logPath =
                        this->mesh().time().path()/"rl_decisions.csv";
                    const bool fresh = !isFile(logPath);
                    OFstream os
                    (
                        logPath,
                        IOstreamOption(IOstreamOption::ASCII),
                        IOstreamOption::APPEND
                    );
                    if (fresh)
                    {
                        os << "time,chemTime,subStep,celli,flag,conf,p,T,P,"
                           << "Y0,Y1,Y2,Y3,Y4,Y5,Y6,Y7,"
                           << "Tprev,Yp0,Yp1,Yp2,Yp3,Yp4,Yp5,Yp6,Yp7,hasPrev,"
                           << "timeSince,tauDec,dtChem"
                           << nl;
                    }
                    for (size_t k = 0; k < active.size(); ++k)
                    {
                        const label celli = active[k];
                        const scalar timeSinceLogged = timeSinceDecision_[celli];
                        double YkeyLog[8];
                        scalar rhoNow = 0;
                        for (label i = 0; i < nSpecie; ++i)
                        {
                            rhoNow += cWork[celli][i]*this->specieThermo_[i].W();
                        }
                        rhoNow = max(rhoNow, SMALL);
                        for (label j = 0; j < 8; ++j)
                        {
                            const label si = keyIndices_[j];
                            YkeyLog[j] =
                                cWork[celli][si]*this->specieThermo_[si].W()/rhoNow;
                        }
                        const bool hasPrev = hasSnapPrev_[celli];
                        os << this->mesh().time().value() << ','
                           << chemTimeAccum_ << ','
                           << s << ','
                           << celli << ','
                           << flags[k] << ','
                           << conf[k] << ','
                           << pQss[k] << ','
                           << Twork[celli] << ','
                           << pWork[celli];
                        for (label j = 0; j < 8; ++j)
                        {
                            os << ',' << YkeyLog[j];
                        }
                        os << ',' << Tprev_[celli];
                        for (label j = 0; j < 8; ++j)
                        {
                            os << ',' << YkeyPrev_[celli][j];
                        }
                        os << ',' << (hasPrev ? 1 : 0)
                           << ',' << timeSinceLogged
                           << ',' << tauDec_
                           << ',' << dtChem
                           << nl;
                    }
                }

                for (size_t k = 0; k < active.size(); ++k)
                {
                    const label celli = active[k];
                    lastDecision_[celli] = flags[k];
                    policyFlag_[celli] = flags[k];
                    forceCvodeHold_[celli] = false; // new τ_dec clears rescue hold
                    everDecided_[celli] = true;

                    double YkeyLog[8];
                    scalar rhoNow = 0;
                    for (label i = 0; i < nSpecie; ++i)
                    {
                        rhoNow += cWork[celli][i]*this->specieThermo_[i].W();
                    }
                    rhoNow = max(rhoNow, SMALL);
                    for (label j = 0; j < 8; ++j)
                    {
                        const label si = keyIndices_[j];
                        YkeyLog[j] =
                            cWork[celli][si]*this->specieThermo_[si].W()/rhoNow;
                    }

                    // Snapshot current state as the prev for the *next* τ_dec query
                    Tprev_[celli] = Twork[celli];
                    for (label j = 0; j < 8; ++j)
                    {
                        YkeyPrev_[celli][j] = YkeyLog[j];
                    }
                    hasSnapPrev_[celli] = true;
                    timeSinceDecision_[celli] = 0;
                    ++nDecisionsTaken_[celli];
                }
            }

            // Predicted action before integrate (policy, unless rescue hold)
            for (label celli = 0; celli < nCells; ++celli)
            {
                policyFlag_[celli] = lastDecision_[celli];
                const bool tryQss =
                    (lastDecision_[celli] == 1) && !forceCvodeHold_[celli];
                solverFlag_[celli] = tryQss ? 1 : 0;
            }
        }
        else if (mode_ == Mode::cvodeOnly)
        {
            forAll(solverFlag_, celli)
            {
                solverFlag_[celli] = 0;
                policyFlag_[celli] = 0;
                lastDecision_[celli] = 0;
                forceCvodeHold_[celli] = false;
            }
        }
        else
        {
            forAll(solverFlag_, celli)
            {
                solverFlag_[celli] = 1;
                policyFlag_[celli] = 1;
                lastDecision_[celli] = 1;
                // qssOnly: re-attempt QSS every window (hold does not stick)
                forceCvodeHold_[celli] = false;
            }
        }

        // --- Integrate one chemistry window ---
        for (label celli = 0; celli < nCells; ++celli)
        {
            if (Twork[celli] <= this->Treact_)
            {
                // Cold cell: still advance the decision clock
                timeSinceDecision_[celli] += dtChem;
                continue;
            }

            for (label i = 0; i < nSpecie; ++i)
            {
                this->c_[i] = cWork[celli][i];
            }
            scalar Ti = Twork[celli];
            scalar pi = pWork[celli];

            const auto t0 = std::chrono::steady_clock::now();
            scalar timeLeft = dtChem;
            const bool policyQss = (lastDecision_[celli] == 1);
            bool tryQss = policyQss && !forceCvodeHold_[celli];
            bool cellUsedCvode = !tryQss;
            bool cellFellBack = false;
            while (timeLeft > SMALL)
            {
                // Re-evaluate if a prior sub-window set the rescue hold
                tryQss = policyQss && !forceCvodeHold_[celli];
                scalar dt = timeLeft;
                scalar subDt = this->deltaTChem_[celli];

                // Layer 1: input sanitation (diagnostic clip mass logged)
                if (guardCoeffs_.enabled)
                {
                    yClipMass_[celli] +=
                        ofRlChem::sanitizeConcentrations(*this, this->c_);
                }

                const scalarField cSnap(this->c_);
                const scalar TSnap = Ti;

                if (tryQss)
                {
                    const bool integOk = ofRlChem::integrateQss
                    (
                        *this, this->c_, Ti, pi, dt, subDt, qssCoeffs_,
                        !guardCoeffs_.enabled,  // floor only if unguarded
                        !guardCoeffs_.enabled   // Euler only if unguarded
                    );

                    bool accept = integOk;
                    word reason = integOk ? "ok" : "qss_integ_fail";
                    ofRlChem::GuardWindowDiag gdiag;
                    if (guardCoeffs_.enabled && integOk)
                    {
                        accept = ofRlChem::acceptQssWindow
                        (
                            *this, cSnap, TSnap, this->c_, Ti,
                            guardCoeffs_, reason, &gdiag
                        );
                    }

                    if (guardCoeffs_.enabled && !accept)
                    {
                        // Layer 2 reject: discard QSS state, redo with CVODE
                        for (label i = 0; i < nSpecie; ++i)
                        {
                            this->c_[i] = cSnap[i];
                        }
                        Ti = TSnap;
#if OF_RL_HAS_SUNDIALS
                        ofRlChem::integrateCvode
                        (
                            *this, this->c_, Ti, pi, dt, subDt,
                            cvodeCoeffs_, cvodeWs_,
                            *static_cast
                                <ofRlChem::CvodeUD
                                    <rlChemistryModel
                                        <ReactionThermo, ThermoType>>*>
                                (cvodeUdStorage_)
                        );
#else
                        FatalErrorInFunction
                            << "QSS guard fallback needs SUNDIALS CVODE"
                            << exit(FatalError);
#endif
                        qssFallbackCount_[celli] += 1;
                        // Reason tally once per cell per CFD solve
                        if (!cellFellBack)
                        {
                            if (reason == "Y_negative")
                            {
                                ++nFbYneg;
                                maxNegY = max(maxNegY, -gdiag.minY);
                            }
                            else if (reason == "sumY_drift")
                            {
                                ++nFbSumY;
                                maxSumDrift = max(maxSumDrift, gdiag.sumYDrift);
                            }
                            else if (reason == "dT_window")
                            {
                                ++nFbDT;
                            }
                            else if (reason == "T_bounds")
                            {
                                ++nFbTbounds;
                            }
                            else
                            {
                                ++nFbInteg; // qss_integ_fail or unknown
                            }
                        }
                        cellUsedCvode = true;
                        cellFellBack = true;
                        // rlAdaptive: hold CVODE until next τ_dec (keep policy flag)
                        if (mode_ == Mode::rlAdaptive)
                        {
                            forceCvodeHold_[celli] = true;
                        }
                    }
                    else if (guardCoeffs_.enabled && accept)
                    {
                        // Accept: floor concentrations for CFD RR
                        for (label i = 0; i < nSpecie; ++i)
                        {
                            this->c_[i] = max(this->c_[i], scalar(0));
                        }
                    }
                }
                else
                {
#if OF_RL_HAS_SUNDIALS
                    ofRlChem::integrateCvode
                    (
                        *this, this->c_, Ti, pi, dt, subDt,
                        cvodeCoeffs_, cvodeWs_,
                        *static_cast
                            <ofRlChem::CvodeUD
                                <rlChemistryModel<ReactionThermo, ThermoType>>*>
                            (cvodeUdStorage_)
                    );
#else
                    FatalErrorInFunction
                        << "CVODE selected but SUNDIALS unavailable"
                        << exit(FatalError);
#endif
                    cellUsedCvode = true;
                }
                this->deltaTChem_[celli] = subDt;
                timeLeft -= dt;
            }
            const auto t1 = std::chrono::steady_clock::now();
            const scalar dCpu =
                std::chrono::duration<double>(t1 - t0).count();
            chemCpuTime_[celli] += dCpu;
            cpuThisSolve[celli] += dCpu;
            if (cellFellBack)
            {
                fellBackThisSolve[celli] = true;
            }

            // Effective usage this chem call; policyFlag stays lastDecision_
            solverFlag_[celli] = cellUsedCvode ? 0 : 1;
            policyFlag_[celli] = lastDecision_[celli];
            if (mode_ == Mode::qssOnly)
            {
                lastDecision_[celli] = 1;
                forceCvodeHold_[celli] = false;
            }
            else if (mode_ == Mode::cvodeOnly)
            {
                lastDecision_[celli] = 0;
                policyFlag_[celli] = 0;
                solverFlag_[celli] = 0;
                forceCvodeHold_[celli] = false;
            }

            for (label i = 0; i < nSpecie; ++i)
            {
                cWork[celli][i] = this->c_[i];
            }
            Twork[celli] = Ti;
            pWork[celli] = pi;

            deltaTMin = min(this->deltaTChem_[celli], deltaTMin);
            this->deltaTChem_[celli] =
                min(this->deltaTChem_[celli], this->deltaTChemMax_);

            // History buffers stay at τ_dec snapshots only (E16.5)
            timeSinceDecision_[celli] += dtChem;
            Tconsistency_[celli] = Ti - T0field[celli];
        }

        chemTimeAccum_ += dtChem;
    }

    // --- Compact usage line (MPI-reduced) for clean logs / progress filters ---
    if (logUsage_)
    {
        label nPolCvode = 0;
        label nPolQss = 0;
        label nEffCvode = 0;
        label nEffQss = 0;
        label nFallback = 0;
        label nHold = 0;
        label nReact = 0;
        scalar cpuCvode = 0;
        scalar cpuQss = 0;
        for (label celli = 0; celli < nCells; ++celli)
        {
            if (T0field[celli] <= this->Treact_)
            {
                continue;
            }
            ++nReact;
            if (lastDecision_[celli] == 0)
            {
                ++nPolCvode;
            }
            else
            {
                ++nPolQss;
            }
            if (forceCvodeHold_[celli])
            {
                ++nHold;
            }
            if (fellBackThisSolve[celli])
            {
                ++nFallback;
            }
            // Attribute CPU by effective solver after last sub-window
            if (solverFlag_[celli] < 0.5)
            {
                ++nEffCvode;
                cpuCvode += cpuThisSolve[celli];
            }
            else
            {
                ++nEffQss;
                cpuQss += cpuThisSolve[celli];
            }
        }

        // Per-rank chem wall ≈ sum of sequential cell timers on that rank.
        // MPI-sum of those = total CPU-seconds; MPI-max ≈ parallel wall chem time.
        const scalar wallChemLocal = cpuCvode + cpuQss;
        scalar wallChem = wallChemLocal;

        reduce(nPolCvode, sumOp<label>());
        reduce(nPolQss, sumOp<label>());
        reduce(nEffCvode, sumOp<label>());
        reduce(nEffQss, sumOp<label>());
        reduce(nFallback, sumOp<label>());
        reduce(nHold, sumOp<label>());
        reduce(nReact, sumOp<label>());
        reduce(nFbYneg, sumOp<label>());
        reduce(nFbSumY, sumOp<label>());
        reduce(nFbDT, sumOp<label>());
        reduce(nFbTbounds, sumOp<label>());
        reduce(nFbInteg, sumOp<label>());
        reduce(maxNegY, maxOp<scalar>());
        reduce(maxSumDrift, maxOp<scalar>());
        reduce(cpuCvode, sumOp<scalar>());
        reduce(cpuQss, sumOp<scalar>());
        reduce(wallChem, maxOp<scalar>());
        scalar policyWallSum = policyWallAcc_;
        scalar policyWallMax = policyWallAcc_;
        reduce(policyWallSum, sumOp<scalar>());
        reduce(policyWallMax, maxOp<scalar>());

        if (Pstream::master())
        {
            const scalar cpuTotSum = cpuCvode + cpuQss;
            const label nProcs = Pstream::nProcs();
            const scalar pct =
                (nFallback > 0)
              ? scalar(100)/scalar(nFallback)
              : scalar(0);
            Info<< "rlUsage"
                << " t=" << this->mesh().time().value()
                << " react=" << nReact
                << " policyCVODE=" << nPolCvode
                << " policyQSS=" << nPolQss
                << " effCVODE=" << nEffCvode
                << " effQSS=" << nEffQss
                << " fallback=" << nFallback
                << " holdCVODE=" << nHold
                << " wall_chem=" << wallChem << "s"
                << " policy_wall_max=" << policyWallMax << "s"
                << " cpu_tot_sum=" << cpuTotSum << "s"
                << " nProcs=" << nProcs
                << endl;
            if (logFallbackReasons_ && nFallback > 0)
            {
                Info<< "rlFallbackReasons"
                    << " Y_negative=" << nFbYneg
                    << " (" << pct*nFbYneg << "%)"
                    << " sumY_drift=" << nFbSumY
                    << " (" << pct*nFbSumY << "%)"
                    << " dT_window=" << nFbDT
                    << " (" << pct*nFbDT << "%)"
                    << " T_bounds=" << nFbTbounds
                    << " (" << pct*nFbTbounds << "%)"
                    << " qss_integ=" << nFbInteg
                    << " (" << pct*nFbInteg << "%)"
                    << " maxNegY=" << maxNegY
                    << " maxSumDrift=" << maxSumDrift
                    << endl;
            }

            // Append step CSV at case root (master only).
            const fileName usagePath =
                this->mesh().time().rootPath()
               /this->mesh().time().globalCaseName()
               /"rl_usage_step.csv";
            // Rotate legacy CSV if columns changed
            if (isFile(usagePath))
            {
                IFstream hdrCheck(usagePath);
                string hdr;
                if (hdrCheck.good())
                {
                    hdrCheck.getLine(hdr);
                    if (hdr.find("policyCVODE") == std::string::npos
                     || hdr.find("policy_wall_max") == std::string::npos)
                    {
                        mv(usagePath, usagePath + ".bak");
                    }
                }
            }
            const bool fresh = !isFile(usagePath);
            OFstream uos
            (
                usagePath,
                IOstreamOption(IOstreamOption::ASCII),
                IOstreamOption::APPEND
            );
            if (fresh)
            {
                uos << "time,nReact,policyCVODE,policyQSS,effCVODE,effQSS,"
                    << "nFallback,nHoldCVODE,"
                    << "fb_Y_negative,fb_sumY_drift,fb_dT_window,"
                    << "fb_T_bounds,fb_qss_integ,maxNegY,maxSumDrift,"
                    << "cpu_CVODE_sum,cpu_QSS_sum,cpu_tot_sum,"
                    << "wall_chem,policy_wall_sum,policy_wall_max,nProcs" << nl;
            }
            uos << this->mesh().time().value() << ','
                << nReact << ','
                << nPolCvode << ','
                << nPolQss << ','
                << nEffCvode << ','
                << nEffQss << ','
                << nFallback << ','
                << nHold << ','
                << nFbYneg << ','
                << nFbSumY << ','
                << nFbDT << ','
                << nFbTbounds << ','
                << nFbInteg << ','
                << maxNegY << ','
                << maxSumDrift << ','
                << cpuCvode << ','
                << cpuQss << ','
                << cpuTotSum << ','
                << wallChem << ','
                << policyWallSum << ','
                << policyWallMax << ','
                << nProcs << nl;
        }
    }

    for (label celli = 0; celli < nCells; ++celli)
    {
        if (T0field[celli] <= this->Treact_)
        {
            for (label i = 0; i < nSpecie; ++i)
            {
                this->RR_[i][celli] = 0;
            }
            continue;
        }
        for (label i = 0; i < nSpecie; ++i)
        {
            this->RR_[i][celli] =
                (cWork[celli][i] - cInit[celli][i])
               *this->specieThermo_[i].W()/deltaT;
        }
    }

    return min(deltaTMin, 2*deltaT);
}


// Explicit instantiation for chemFoam thermo set
#include "psiReactionThermo.H"
#include "thermoPhysicsTypes.H"

template class Foam::rlChemistryModel
<
    Foam::psiReactionThermo,
    Foam::gasHThermoPhysics
>;

// ************************************************************************* //
