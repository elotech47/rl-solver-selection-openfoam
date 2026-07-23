/**
 * @file rlIntegrators.H
 * Per-cell QSS / CVODE helpers for rlChemistryModel (adapted from qss/cvode solvers).
 */

#ifndef rlIntegrators_H
#define rlIntegrators_H

#include "qss_int.H"
#include "ofRlInvariants.H"
#include "Switch.H"

#if __has_include(<cvode/cvode.h>)
#   define OF_RL_HAS_SUNDIALS 1
#   include <cvode/cvode.h>
#   include <nvector/nvector_serial.h>
#   include <sunmatrix/sunmatrix_dense.h>
#   include <sunlinsol/sunlinsol_dense.h>
#   include <sundials/sundials_types.h>
#   include <sundials/sundials_context.h>
#else
#   define OF_RL_HAS_SUNDIALS 0
#endif

namespace ofRlChem
{

struct QssCoeffs
{
    Foam::scalar epsmin{0.02};
    Foam::scalar epsmax{100};
    Foam::scalar dtmin{1e-12};
    Foam::scalar dtmax{1e-6};
    Foam::scalar abstol{1e-11};
    Foam::label itermax{2};
    bool Tfreeze{true};
};

struct CvodeCoeffs
{
    Foam::scalar rtol{1e-8};
    Foam::scalar atol{1e-12};
    Foam::label mxsteps{100000};
};

/** E17.2 chemistry-level guards (dictionary: guardCoeffs). */
struct GuardCoeffs
{
    bool enabled{true};
    // Defaults relaxed 2026-07-22: 1e-12 / 1e-3 rejected ~90% of QSS
    // windows on raw CHEMEQ2 output (tiny negatives / ΣY drift). Layer-1
    // still floors+renorms on accept; these only gate the CVODE rescue.
    Foam::scalar epsY{1e-8};        // reject if any Y_i < -epsY
    Foam::scalar epsSumY{1e-2};     // reject if |ΣY−1| > epsSumY
    Foam::scalar dTmaxWindow{500};  // K per chemistry micro-window
    Foam::scalar TminAccept{310};
    Foam::scalar TmaxAccept{3400};
};

/** Diagnostics from one Layer-2 evaluation (filled even on accept). */
struct GuardWindowDiag
{
    Foam::scalar minY{0};       // min_i Y_i (signed)
    Foam::scalar sumYDrift{0};  // |ΣY−1|
    Foam::scalar dT{0};         // |T1−T0|
};

/**
 * Layer 1 — floor Y_i≥0 and renormalize ΣY=1 (keeps mixture ρ).
 * Returns clipped negative mass fraction sum (diagnostic).
 */
template<class ChemistryModel>
inline Foam::scalar sanitizeConcentrations
(
    const ChemistryModel& model,
    Foam::scalarField& c
)
{
    const Foam::label nSpecie = model.nSpecie();
    Foam::scalar rho = 0.0;
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        rho += c[i]*model.specieThermo()[i].W();
    }
    rho = Foam::max(rho, Foam::SMALL);

    Foam::scalarField Y(nSpecie, 0.0);
    Foam::scalar clipped = 0.0;
    Foam::scalar sumPos = 0.0;
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        Y[i] = c[i]*model.specieThermo()[i].W()/rho;
        if (Y[i] < 0)
        {
            clipped += -Y[i];
            Y[i] = 0;
        }
        sumPos += Y[i];
    }
    if (sumPos > Foam::SMALL)
    {
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            Y[i] /= sumPos;
            c[i] = rho*Y[i]/model.specieThermo()[i].W();
        }
    }
    return clipped;
}

/** Mass fractions from concentrations (signed; no floor). */
template<class ChemistryModel>
inline void concentrationsToY
(
    const ChemistryModel& model,
    const Foam::scalarField& c,
    Foam::scalarField& Y,
    Foam::scalar& sumY
)
{
    const Foam::label nSpecie = model.nSpecie();
    Foam::scalar rhoSigned = 0.0;
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        rhoSigned += c[i]*model.specieThermo()[i].W();
    }
    const Foam::scalar rhoDen = Foam::max(Foam::mag(rhoSigned), Foam::SMALL);
    Y.setSize(nSpecie);
    sumY = 0.0;
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        Y[i] = c[i]*model.specieThermo()[i].W()/rhoDen;
        sumY += Y[i];
    }
}

/**
 * Layer 2 — QSS acceptance after a micro-window (raw concentrations, pre-floor).
 * First failing check wins (order: Y → ΣY → dT → T bounds).
 */
template<class ChemistryModel>
inline bool acceptQssWindow
(
    const ChemistryModel& model,
    const Foam::scalarField& /*c0*/,
    const Foam::scalar T0,
    const Foam::scalarField& c1,
    const Foam::scalar T1,
    const GuardCoeffs& g,
    Foam::word& reason,
    GuardWindowDiag* diag = nullptr
)
{
    Foam::scalarField Y;
    Foam::scalar sumY = 0;
    concentrationsToY(model, c1, Y, sumY);

    Foam::scalar minY = Foam::GREAT;
    forAll(Y, i)
    {
        minY = Foam::min(minY, Y[i]);
    }
    const Foam::scalar sumDrift = Foam::mag(sumY - Foam::scalar(1));
    const Foam::scalar dT = Foam::mag(T1 - T0);
    if (diag)
    {
        diag->minY = minY;
        diag->sumYDrift = sumDrift;
        diag->dT = dT;
    }

    if (minY < -g.epsY)
    {
        reason = "Y_negative";
        return false;
    }
    if (sumDrift > g.epsSumY)
    {
        reason = "sumY_drift";
        return false;
    }
    if (dT > g.dTmaxWindow)
    {
        reason = "dT_window";
        return false;
    }
    if (T1 < g.TminAccept || T1 > g.TmaxAccept)
    {
        reason = "T_bounds";
        return false;
    }
    reason = "ok";
    return true;
}

inline Foam::scalar suggestDeltaT(Foam::scalar deltaT, Foam::scalar dTwin)
{
    const Foam::scalar dTmax = 25.0;
    return deltaT*Foam::min
    (
        Foam::max(dTmax/Foam::max(dTwin, Foam::SMALL), Foam::scalar(0.05)),
        Foam::scalar(2)
    );
}

template<class ChemistryModel>
class QssCellOde : public QssOde
{
    const ChemistryModel& model_;
    Foam::scalar p_;
    const bool Tfreeze_;
    Foam::scalar T_cache_{0};
    Foam::scalar rho_cache_{0};
    Foam::scalar cp_cache_{0};
    Foam::scalarField ha_cache_;
    bool haveCache_{false};

public:
    QssCellOde(const ChemistryModel& model, Foam::scalar p, bool Tfreeze)
    :
        model_(model),
        p_(p),
        Tfreeze_(Tfreeze),
        ha_cache_(model.nSpecie(), 0.0)
    {}

    virtual void odefun
    (
        double /*t*/,
        const std::vector<double>& y,
        std::vector<double>& q,
        std::vector<double>& d,
        bool corrector
    ) override
    {
        const Foam::label nSpecie = model_.nSpecie();
        const Foam::scalar T_in =
            Foam::min(Foam::max(y[0], Foam::scalar(250)), Foam::scalar(4500));

        Foam::scalarField c(nSpecie, 0.0);
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            c[i] = Foam::max(y[static_cast<size_t>(i) + 1], 0.0);
        }

        const bool freezeNow = Tfreeze_ && corrector && haveCache_;
        const Foam::scalar T = freezeNow ? T_cache_ : T_in;

        Foam::scalar rho = 0.0;
        Foam::scalar cp = 0.0;

        if (!freezeNow)
        {
            for (Foam::label i = 0; i < nSpecie; ++i)
            {
                rho += c[i]*model_.specieThermo()[i].W();
            }
            rho = Foam::max(rho, Foam::SMALL);
            for (Foam::label i = 0; i < nSpecie; ++i)
            {
                cp += c[i]*model_.specieThermo()[i].cp(p_, T);
                ha_cache_[i] = model_.specieThermo()[i].ha(p_, T);
            }
            cp /= rho;
            cp = Foam::max(cp, Foam::SMALL);
            T_cache_ = T;
            rho_cache_ = rho;
            cp_cache_ = cp;
            haveCache_ = true;
        }
        else
        {
            rho = rho_cache_;
            cp = cp_cache_;
        }

        Foam::scalarField qC(nSpecie, 0.0);
        Foam::scalarField dC(nSpecie, 0.0);
        const auto& reactions = model_.reactions();
        forAll(reactions, ri)
        {
            Foam::scalar pf = 0, cf = 0, pr = 0, cr = 0;
            Foam::label lRef = 0, rRef = 0;
            model_.omegaI(ri, c, T, p_, pf, cf, lRef, pr, cr, rRef);
            const Foam::scalar omegaf = pf*cf;
            const Foam::scalar omegar = pr*cr;
            const auto& R = reactions[ri];
            forAll(R.lhs(), s)
            {
                const Foam::label si = R.lhs()[s].index;
                const Foam::scalar nu = R.lhs()[s].stoichCoeff;
                dC[si] += omegaf*nu;
                qC[si] += omegar*nu;
            }
            forAll(R.rhs(), s)
            {
                const Foam::label si = R.rhs()[s].index;
                const Foam::scalar nu = R.rhs()[s].stoichCoeff;
                qC[si] += omegaf*nu;
                dC[si] += omegar*nu;
            }
        }

        q.assign(static_cast<size_t>(nSpecie) + 1, 0.0);
        d.assign(static_cast<size_t>(nSpecie) + 1, 0.0);
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            q[static_cast<size_t>(i) + 1] = Foam::max(qC[i], 0.0);
            d[static_cast<size_t>(i) + 1] = Foam::max(dC[i], 0.0);
        }

        Foam::scalar dT = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            const Foam::scalar ha =
                freezeNow ? ha_cache_[i] : model_.specieThermo()[i].ha(p_, T);
            dT += ha*(qC[i] - dC[i]);
        }
        dT /= rho*cp;
        q[0] = -dT;
        d[0] = 0.0;
    }
};

template<class ChemistryModel>
inline bool integrateQss
(
    ChemistryModel& model,
    Foam::scalarField& c,
    Foam::scalar& T,
    Foam::scalar& p,
    Foam::scalar& deltaT,
    Foam::scalar& subDeltaT,
    const QssCoeffs& coeffs,
    const bool applyNonnegFloor = true,
    const bool eulerOnFail = true
)
{
    const Foam::label nSpecie = model.nSpecie();
    const Foam::scalar T0in = T;
    Foam::scalarField c0snap(nSpecie);
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        c[i] = Foam::max(c[i], Foam::scalar(0));
        c0snap[i] = c[i];
    }

    std::vector<double> y(static_cast<size_t>(nSpecie) + 1);
    y[0] = T;
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        y[static_cast<size_t>(i) + 1] = c[i];
    }

    QssIntegrator integ;
    integ.epsmin = coeffs.epsmin;
    integ.epsmax = coeffs.epsmax;
    integ.dtmin = coeffs.dtmin;
    integ.dtmax = Foam::min(coeffs.dtmax, Foam::mag(deltaT));
    integ.abstol = coeffs.abstol;
    integ.itermax = coeffs.itermax;
    integ.initialize(y.size());
    integ.enforce_ymin[0] = 0.0;
    integ.ymin[0] = 200.0;
    integ.enforce_ymax[0] = 1.0;
    integ.ymax[0] = 5000.0;

    QssCellOde<ChemistryModel> ode(model, p, coeffs.Tfreeze);
    integ.setOde(&ode);
    integ.setState(y, 0.0);

    const int ret = integ.integrateToTime(deltaT);
    if (ret != 0)
    {
        if (!eulerOnFail)
        {
            // Caller (E17.2 guards) will restore + CVODE.
            subDeltaT = suggestDeltaT(deltaT, Foam::scalar(0));
            return false;
        }
        WarningInFunction
            << "α-QSS failed (ret=" << ret << "); explicit Euler fallback"
            << Foam::endl;
        Foam::scalarField dcdt(nSpecie, Foam::Zero);
        model.omega(c, T, p, dcdt);
        Foam::scalar rho = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            rho += c[i]*model.specieThermo()[i].W();
        }
        rho = Foam::max(rho, Foam::SMALL);
        Foam::scalar cp = 0.0;
        Foam::scalar dT = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            cp += c[i]*model.specieThermo()[i].cp(p, T);
            dT += model.specieThermo()[i].ha(p, T)*dcdt[i];
            c[i] = Foam::max(c[i] + deltaT*dcdt[i], Foam::scalar(0));
        }
        cp /= rho;
        cp = Foam::max(cp, Foam::SMALL);
        T = T - deltaT*dT/(rho*cp);
        T = Foam::min(Foam::max(T, Foam::scalar(250)), Foam::scalar(4500));
        Foam::ofRlInvariants::recordSolve(T0in, T, deltaT, c0snap, c);
        subDeltaT = suggestDeltaT(deltaT, Foam::mag(T - T0in));
        return true;
    }

    integ.getState(y);
    T = y[0];
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        const Foam::scalar ci = y[static_cast<size_t>(i) + 1];
        c[i] = applyNonnegFloor ? Foam::max(ci, Foam::scalar(0)) : ci;
    }
    Foam::ofRlInvariants::recordSolve(T0in, T, deltaT, c0snap, c);
    subDeltaT = suggestDeltaT(deltaT, Foam::mag(T - T0in));
    return true;
}

// Always-declared UD so headers compile without SUNDIALS
template<class ChemistryModel>
struct CvodeUD
{
    const ChemistryModel* model{nullptr};
    Foam::label nSpecie{0};
};

#if OF_RL_HAS_SUNDIALS

template<class ChemistryModel>
inline int cvodeRhsRl
(
    sunrealtype /*t*/,
    N_Vector y,
    N_Vector ydot,
    void* user_data
)
{
    auto* ud = static_cast<CvodeUD<ChemistryModel>*>(user_data);
    const Foam::label n = ud->nSpecie;
    Foam::scalarField c(n);
    for (Foam::label i = 0; i < n; ++i)
    {
        c[i] = Foam::max(NV_Ith_S(y, i), 0.0);
    }
    Foam::scalar T = Foam::min(Foam::max(NV_Ith_S(y, n), 250.0), 4500.0);
    Foam::scalar p = NV_Ith_S(y, n + 1);
    Foam::scalarField dcdt(n, 0.0);
    ud->model->omega(c, T, p, dcdt);
    Foam::scalar rho = 0.0;
    for (Foam::label i = 0; i < n; ++i)
    {
        rho += c[i]*ud->model->specieThermo()[i].W();
    }
    rho = Foam::max(rho, Foam::SMALL);
    Foam::scalar cp = 0.0;
    for (Foam::label i = 0; i < n; ++i)
    {
        cp += c[i]*ud->model->specieThermo()[i].cp(p, T);
        NV_Ith_S(ydot, i) = dcdt[i];
    }
    cp /= rho;
    cp = Foam::max(cp, Foam::SMALL);
    Foam::scalar dT = 0.0;
    for (Foam::label i = 0; i < n; ++i)
    {
        dT += ud->model->specieThermo()[i].ha(p, T)*dcdt[i];
    }
    dT /= rho*cp;
    NV_Ith_S(ydot, n) = -dT;
    NV_Ith_S(ydot, n + 1) = 0.0;
    return 0;
}

#endif

/** Persistent CVODE workspace (one per chemistry model instance). */
struct CvodeWorkspace
{
#if OF_RL_HAS_SUNDIALS
    SUNContext sunctx = nullptr;
    N_Vector y = nullptr;
    SUNMatrix A = nullptr;
    SUNLinearSolver LS = nullptr;
    void* mem = nullptr;
    sunindextype neq = 0;

    ~CvodeWorkspace()
    {
        if (LS) SUNLinSolFree(LS);
        if (A) SUNMatDestroy(A);
        if (mem) CVodeFree(&mem);
        if (y) N_VDestroy(y);
        if (sunctx) SUNContext_Free(&sunctx);
    }
#endif
};

template<class ChemistryModel>
inline void integrateCvode
(
    ChemistryModel& model,
    Foam::scalarField& c,
    Foam::scalar& T,
    Foam::scalar& p,
    Foam::scalar& deltaT,
    Foam::scalar& subDeltaT,
    const CvodeCoeffs& coeffs,
    CvodeWorkspace& ws,
    CvodeUD<ChemistryModel>& ud
)
{
#if !OF_RL_HAS_SUNDIALS
    FatalErrorInFunction
        << "CVODE requires SUNDIALS"
        << Foam::exit(Foam::FatalError);
#else
    const Foam::label nSpecie = model.nSpecie();
    const sunindextype neq = nSpecie + 2;
    const Foam::scalar T0 = T;
    Foam::scalarField c0snap(nSpecie);
    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        c0snap[i] = Foam::max(c[i], Foam::scalar(0));
    }

    if (!ws.mem)
    {
        ws.neq = neq;
        if (SUNContext_Create(nullptr, &ws.sunctx) < 0)
        {
            FatalErrorInFunction << "SUNContext_Create failed"
                << Foam::exit(Foam::FatalError);
        }
        ws.y = N_VNew_Serial(neq, ws.sunctx);
        ud.model = &model;
        ud.nSpecie = nSpecie;
        ws.mem = CVodeCreate(CV_BDF, ws.sunctx);
        CVodeInit(ws.mem, cvodeRhsRl<ChemistryModel>, 0.0, ws.y);
        CVodeSStolerances(ws.mem, coeffs.rtol, coeffs.atol);
        CVodeSetUserData(ws.mem, &ud);
        CVodeSetMaxNumSteps(ws.mem, coeffs.mxsteps);
        ws.A = SUNDenseMatrix(neq, neq, ws.sunctx);
        ws.LS = SUNLinSol_Dense(ws.y, ws.A, ws.sunctx);
        CVodeSetLinearSolver(ws.mem, ws.LS, ws.A);
    }
    else
    {
        ud.model = &model;
        ud.nSpecie = nSpecie;
    }

    for (Foam::label i = 0; i < nSpecie; ++i)
    {
        NV_Ith_S(ws.y, i) = Foam::max(c[i], Foam::scalar(0));
    }
    NV_Ith_S(ws.y, nSpecie) = T;
    NV_Ith_S(ws.y, nSpecie + 1) = p;
    CVodeReInit(ws.mem, 0.0, ws.y);

    sunrealtype tOut = 0.0;
    const int flag = CVode(ws.mem, deltaT, ws.y, &tOut, CV_NORMAL);
    if (flag < 0)
    {
        WarningInFunction
            << "CVODE failed flag=" << flag << "; leaving state unchanged"
            << Foam::endl;
    }
    else
    {
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            c[i] = Foam::max(NV_Ith_S(ws.y, i), Foam::scalar(0));
        }
        T = Foam::min(Foam::max(NV_Ith_S(ws.y, nSpecie), Foam::scalar(250)), Foam::scalar(4500));
        p = NV_Ith_S(ws.y, nSpecie + 1);
    }

    Foam::ofRlInvariants::recordSolve(T0, T, deltaT, c0snap, c);
    subDeltaT = suggestDeltaT(deltaT, Foam::mag(T - T0));
#endif
}

} // namespace ofRlChem

#endif
