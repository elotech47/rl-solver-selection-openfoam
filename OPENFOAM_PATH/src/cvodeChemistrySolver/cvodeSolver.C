/*---------------------------------------------------------------------------*\
  SUNDIALS CVODE chemistrySolver (ESI v2312, SUNDIALS ≥ 6)
\*---------------------------------------------------------------------------*/

#include "cvodeSolver.H"
#include "ofRlInvariants.H"

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

// * * * * * * * * * * * * * Persistent SUNDIALS state * * * * * * * * * * * //

#if OF_RL_HAS_SUNDIALS

namespace
{
template<class ChemistryModel>
struct CvodeUD
{
    const ChemistryModel* model;
    Foam::label nSpecie;
};

template<class ChemistryModel>
int cvodeRhs
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
    // Clamp T to the JANAF-valid band so transient overshoot during the
    // runaway cannot push property evaluation into garbage extrapolation.
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

    // Constant-pressure energy equation, identical to ESI
    // StandardChemistryModel::derivatives(): dT/dt = -Σ ha_i ω̇_i / (ρ cp).
    // Using absolute enthalpy ha (formation + sensible) conserves enthalpy;
    // an Hc-only source overshoots past the adiabatic flame temperature.
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
} // namespace

#endif


template<class ChemistryModel>
struct Foam::cvode<ChemistryModel>::Impl
{
#if OF_RL_HAS_SUNDIALS
    SUNContext sunctx = nullptr;
    N_Vector y = nullptr;
    SUNMatrix A = nullptr;
    SUNLinearSolver LS = nullptr;
    void* mem = nullptr;
    CvodeUD<ChemistryModel> ud{};
    sunindextype neq = 0;

    ~Impl()
    {
        if (LS) SUNLinSolFree(LS);
        if (A) SUNMatDestroy(A);
        if (mem) CVodeFree(&mem);
        if (y) N_VDestroy(y);
        if (sunctx) SUNContext_Free(&sunctx);
    }
#endif
};


// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class ChemistryModel>
Foam::cvode<ChemistryModel>::cvode
(
    typename ChemistryModel::reactionThermo& thermo
)
:
    chemistrySolver<ChemistryModel>(thermo),
    coeffsDict_(this->subDict("cvodeCoeffs")),
    rtol_(coeffsDict_.getOrDefault<scalar>("relTol", 1e-8)),
    atol_(coeffsDict_.getOrDefault<scalar>("absTol", 1e-12)),
    mxsteps_(coeffsDict_.getOrDefault<label>("maxSteps", 100000)),
    impl_(nullptr)
{}


template<class ChemistryModel>
Foam::cvode<ChemistryModel>::~cvode()
{
    delete impl_;
}


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

template<class ChemistryModel>
void Foam::cvode<ChemistryModel>::solve
(
    scalarField& c,
    scalar& T,
    scalar& p,
    scalar& deltaT,
    scalar& subDeltaT
) const
{
#if !OF_RL_HAS_SUNDIALS
    FatalErrorInFunction
        << "cvode chemistrySolver requires SUNDIALS (set SUNDIALS_DIR)."
        << exit(FatalError);
#else
    const label nSpecie = this->nSpecie();
    const sunindextype neq = nSpecie + 2;
    const scalar T0 = T;
    scalarField c0snap(nSpecie);
    for (label i = 0; i < nSpecie; ++i)
    {
        c0snap[i] = max(c[i], scalar(0));
    }

    if (!impl_)
    {
        impl_ = new Impl();
        Impl& s = *impl_;
        s.neq = neq;

        if (SUNContext_Create(nullptr, &s.sunctx) < 0)
        {
            FatalErrorInFunction << "SUNContext_Create failed"
                << exit(FatalError);
        }
        s.y = N_VNew_Serial(neq, s.sunctx);
        s.ud.model = static_cast<const ChemistryModel*>(this);
        s.ud.nSpecie = nSpecie;

        s.mem = CVodeCreate(CV_BDF, s.sunctx);
        CVodeInit(s.mem, cvodeRhs<ChemistryModel>, 0.0, s.y);
        CVodeSStolerances(s.mem, rtol_, atol_);
        CVodeSetUserData(s.mem, &s.ud);
        CVodeSetMaxNumSteps(s.mem, mxsteps_);

        s.A = SUNDenseMatrix(neq, neq, s.sunctx);
        s.LS = SUNLinSol_Dense(s.y, s.A, s.sunctx);
        CVodeSetLinearSolver(s.mem, s.LS, s.A);
    }

    Impl& s = *impl_;

    for (label i = 0; i < nSpecie; ++i)
    {
        NV_Ith_S(s.y, i) = max(c[i], scalar(0));
    }
    NV_Ith_S(s.y, nSpecie) = T;
    NV_Ith_S(s.y, nSpecie + 1) = p;

    // Re-initialise state only; Jacobian/step-size history is reset but all
    // workspace allocations are reused.
    CVodeReInit(s.mem, 0.0, s.y);

    sunrealtype tOut = 0.0;
    const int flag = CVode(s.mem, deltaT, s.y, &tOut, CV_NORMAL);
    if (flag < 0)
    {
        WarningInFunction
            << "CVODE failed flag=" << flag << "; leaving state unchanged"
            << endl;
    }
    else
    {
        for (label i = 0; i < nSpecie; ++i)
        {
            c[i] = max(NV_Ith_S(s.y, i), scalar(0));
        }
        T = min(max(NV_Ith_S(s.y, nSpecie), scalar(250)), scalar(4500));
        p = NV_Ith_S(s.y, nSpecie + 1);
    }

    ofRlInvariants::recordSolve(T0, T, deltaT, c0snap, c);

    // Suggest the next chemistry window so |dT| per window stays ~<= dTmax.
    // Keeps chemFoam's h->T Newton close to its solution during the ignition
    // runaway (stock chemFoam aborts if one window swallows the whole spike),
    // and lets the step grow back (2x cap applied by StandardChemistryModel).
    const scalar dTmax = 25.0;
    const scalar dTwin = mag(T - T0);
    subDeltaT = deltaT*min(max(dTmax/max(dTwin, SMALL), scalar(0.05)), scalar(2));
#endif
}

// ************************************************************************* //
