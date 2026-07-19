/*---------------------------------------------------------------------------*\
  α-QSS chemistrySolver implementation (ESI v2312)
\*---------------------------------------------------------------------------*/

#include "qss.H"
#include "ofRlInvariants.H"

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class ChemistryModel>
Foam::qss<ChemistryModel>::qss
(
    typename ChemistryModel::reactionThermo& thermo
)
:
    chemistrySolver<ChemistryModel>(thermo),
    coeffsDict_(this->subDict("qssCoeffs")),
    epsmin_(coeffsDict_.getOrDefault<scalar>("epsmin", 0.02)),
    epsmax_(coeffsDict_.getOrDefault<scalar>("epsmax", 100)),
    dtmin_(coeffsDict_.getOrDefault<scalar>("dtmin", 1e-12)),
    dtmax_(coeffsDict_.getOrDefault<scalar>("dtmax", 1e-6)),
    abstol_(coeffsDict_.getOrDefault<scalar>("abstol", 1e-11)),
    itermax_(coeffsDict_.getOrDefault<label>("itermax", 2))
{}


template<class ChemistryModel>
Foam::qss<ChemistryModel>::~qss()
{}


// * * * * * * * * * * * * * * ODE adapter (true q/d from FR rates)  * * * * * //

namespace
{

template<class ChemistryModel>
class QssCellOde
:
    public ofRlChem::QssOde
{
    const ChemistryModel& model_;
    Foam::scalar p_;

public:

    QssCellOde(const ChemistryModel& model, Foam::scalar p)
    :
        model_(model),
        p_(p)
    {}

    virtual void odefun
    (
        double /*t*/,
        const std::vector<double>& y,
        std::vector<double>& q,
        std::vector<double>& d,
        bool /*corrector*/
    ) override
    {
        const Foam::label nSpecie = model_.nSpecie();
        // Clamp T to the JANAF-valid band (transient overshoot protection)
        Foam::scalar T =
            Foam::min(Foam::max(y[0], Foam::scalar(250)), Foam::scalar(4500));

        // Concentrations; size nSpecie (OF omegaI/omega convention)
        Foam::scalarField c(nSpecie, 0.0);
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            c[i] = Foam::max(y[static_cast<size_t>(i) + 1], 0.0);
        }

        Foam::scalar rho = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            rho += c[i]*model_.specieThermo()[i].W();
        }
        rho = Foam::max(rho, Foam::SMALL);

        Foam::scalarField qC(nSpecie, 0.0);
        Foam::scalarField dC(nSpecie, 0.0);

        const auto& reactions = model_.reactions();
        forAll(reactions, ri)
        {
            Foam::scalar pf = 0, cf = 0, pr = 0, cr = 0;
            Foam::label lRef = 0, rRef = 0;
            model_.omegaI(ri, c, T, p_, pf, cf, lRef, pr, cr, rRef);

            // ESI omegaI: net ω = pf*cf - pr*cr (pf/pr omit the ref species).
            // Use full forward/reverse progress rates for true q/d.
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
            // Clamp tiny negative round-off in q/d
            q[static_cast<size_t>(i) + 1] = Foam::max(qC[i], 0.0);
            d[static_cast<size_t>(i) + 1] = Foam::max(dC[i], 0.0);
        }

        // Constant-pressure energy equation matching ESI
        // StandardChemistryModel::derivatives(): dT/dt = -Σ ha_i ω̇_i/(ρ cp)
        // (absolute enthalpy ha, mole basis; conserves enthalpy).
        Foam::scalar cp = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            cp += c[i]*model_.specieThermo()[i].cp(p_, T);
        }
        cp /= rho;
        cp = Foam::max(cp, Foam::SMALL);

        Foam::scalar dT = 0.0;
        for (Foam::label i = 0; i < nSpecie; ++i)
        {
            dT += model_.specieThermo()[i].ha(p_, T)*(qC[i] - dC[i]);
        }
        dT /= rho*cp;

        // Temperature: evolve with net heat release (no Padé on T)
        q[0] = -dT;
        d[0] = 0.0;
    }
};

// Suggest next chemistry window so |dT| per window stays ~<= 25 K
// (keeps chemFoam's h->T Newton near its solution through ignition;
// growth is capped at 2x per step by StandardChemistryModel).
static Foam::scalar suggestDeltaT(Foam::scalar deltaT, Foam::scalar dTwin)
{
    const Foam::scalar dTmax = 25.0;
    return deltaT*Foam::min
    (
        Foam::max(dTmax/Foam::max(dTwin, Foam::SMALL), Foam::scalar(0.05)),
        Foam::scalar(2)
    );
}

} // namespace


// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //

template<class ChemistryModel>
void Foam::qss<ChemistryModel>::solve
(
    scalarField& c,
    scalar& T,
    scalar& p,
    scalar& deltaT,
    scalar& subDeltaT
) const
{
    const label nSpecie = this->nSpecie();
    const scalar T0in = T;
    scalarField c0snap(nSpecie);
    for (label i = 0; i < nSpecie; ++i)
    {
        c[i] = max(c[i], scalar(0));
        c0snap[i] = c[i];
    }

    std::vector<double> y(static_cast<size_t>(nSpecie) + 1);
    y[0] = T;
    for (label i = 0; i < nSpecie; ++i)
    {
        y[static_cast<size_t>(i) + 1] = c[i];
    }

    ofRlChem::QssIntegrator integ;
    integ.epsmin = epsmin_;
    integ.epsmax = epsmax_;
    integ.dtmin = dtmin_;
    integ.dtmax = min(dtmax_, mag(deltaT));
    integ.abstol = abstol_;
    integ.itermax = itermax_;
    integ.initialize(y.size());
    // Temperature: net ODE (no ymin floor); species: floor
    integ.enforce_ymin[0] = 0.0;
    integ.ymin[0] = 200.0;
    integ.enforce_ymax[0] = 1.0;
    integ.ymax[0] = 5000.0;

    QssCellOde<ChemistryModel> ode(*this, p);
    integ.setOde(&ode);
    integ.setState(y, 0.0);

    const int ret = integ.integrateToTime(deltaT);
    if (ret != 0)
    {
        // Do not silently freeze: take an explicit Euler step with net omega
        // so the CFD energy path still sees a consistent source, and log it.
        WarningInFunction
            << "α-QSS failed (ret=" << ret
            << ") at T=" << T << " p=" << p
            << "; falling back to explicit Euler with net ω for this window"
            << endl;

        scalarField dcdt(nSpecie, Zero);
        this->omega(c, T, p, dcdt);

        scalar rho = 0.0;
        for (label i = 0; i < nSpecie; ++i)
        {
            rho += c[i]*this->specieThermo()[i].W();
        }
        rho = max(rho, SMALL);

        // Same constant-pressure ha-based energy source as the main ODE
        scalar cp = 0.0;
        scalar dT = 0.0;
        for (label i = 0; i < nSpecie; ++i)
        {
            cp += c[i]*this->specieThermo()[i].cp(p, T);
            dT += this->specieThermo()[i].ha(p, T)*dcdt[i];
            c[i] = max(c[i] + deltaT*dcdt[i], scalar(0));
        }
        cp /= rho;
        cp = max(cp, SMALL);
        T = T - deltaT*dT/(rho*cp);
        T = min(max(T, scalar(250)), scalar(4500));

        ofRlInvariants::recordSolve(T0in, T, deltaT, c0snap, c);
        subDeltaT = suggestDeltaT(deltaT, mag(T - T0in));
        return;
    }

    integ.getState(y);
    T = y[0];
    for (label i = 0; i < nSpecie; ++i)
    {
        c[i] = max(y[static_cast<size_t>(i) + 1], scalar(0));
    }

    ofRlInvariants::recordSolve(T0in, T, deltaT, c0snap, c);
    subDeltaT = suggestDeltaT(deltaT, mag(T - T0in));
}

// ************************************************************************* //
