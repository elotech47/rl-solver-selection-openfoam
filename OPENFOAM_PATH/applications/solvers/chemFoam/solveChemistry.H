{
    // Density used to form RR / concentrations inside chemistry.solve
    rhoChemUsed = rho[0];

    // E13.2 / E7: dump instantaneous ω̇ at the current cell state (before integrate).
    if (Foam::getEnv("OFRL_DUMP_RATES") == "1")
    {
        const label nSpecie = chemistry.nSpecie();
        scalarField c(nSpecie);
        for (label i = 0; i < nSpecie; ++i)
        {
            c[i] = max(Y[i][0]*rho[0]/specieData[i].W(), scalar(0));
        }
        scalarField dcdt(nSpecie, Zero);
        typedef StandardChemistryModel<psiReactionThermo, gasHThermoPhysics>
            stdChemType;
        const stdChemType& stdChem = refCast<const stdChemType>(chemistry);
        stdChem.omega(c, thermo.T()[0], p[0], dcdt);

        const auto& reactions = stdChem.reactions();
        const label nReac = reactions.size();
        const scalar Tdump = thermo.T()[0];
        const scalar Pdump = p[0];

        OFstream os(runTime.path()/"of_rates_dump.json");
        os << "{\n"
           << "  \"T\": " << Tdump << ",\n"
           << "  \"P\": " << Pdump << ",\n"
           << "  \"nSpecie\": " << nSpecie << ",\n"
           << "  \"nReaction\": " << nReac << ",\n"
           << "  \"species\": [";
        for (label i = 0; i < nSpecie; ++i)
        {
            os << (i ? ", " : "") << "\"" << Y[i].name() << "\"";
        }
        os << "],\n  \"Y\": [";
        for (label i = 0; i < nSpecie; ++i)
        {
            os << (i ? ", " : "") << Y[i][0];
        }
        os << "],\n  \"of_net\": [";
        for (label i = 0; i < nSpecie; ++i)
        {
            os << (i ? ", " : "") << dcdt[i];
        }
        // E7-proper: per-reaction kf, kr, Kc, ROP
        os << "],\n  \"kf\": [";
        for (label ri = 0; ri < nReac; ++ri)
        {
            const scalar kf = reactions[ri].kf(Pdump, Tdump, c);
            os << (ri ? ", " : "") << kf;
        }
        os << "],\n  \"kr\": [";
        for (label ri = 0; ri < nReac; ++ri)
        {
            const scalar kf = reactions[ri].kf(Pdump, Tdump, c);
            const scalar kr = reactions[ri].kr(kf, Pdump, Tdump, c);
            os << (ri ? ", " : "") << kr;
        }
        os << "],\n  \"Kc\": [";
        for (label ri = 0; ri < nReac; ++ri)
        {
            const scalar kf = reactions[ri].kf(Pdump, Tdump, c);
            const scalar kr = reactions[ri].kr(kf, Pdump, Tdump, c);
            const scalar Kc =
                (mag(kr) > SMALL) ? kf/kr : scalar(0);
            os << (ri ? ", " : "") << Kc;
        }
        os << "],\n  \"qf\": [";
        for (label ri = 0; ri < nReac; ++ri)
        {
            scalar pf = 0, cf = 0, pr = 0, cr = 0;
            label lRef = 0, rRef = 0;
            stdChem.omegaI(ri, c, Tdump, Pdump, pf, cf, lRef, pr, cr, rRef);
            os << (ri ? ", " : "") << (pf*cf);
        }
        os << "],\n  \"qr\": [";
        for (label ri = 0; ri < nReac; ++ri)
        {
            scalar pf = 0, cf = 0, pr = 0, cr = 0;
            label lRef = 0, rRef = 0;
            stdChem.omegaI(ri, c, Tdump, Pdump, pf, cf, lRef, pr, cr, rRef);
            os << (ri ? ", " : "") << (pr*cr);
        }
        os << "]\n}\n";
        os.flush();
        Info<< "Wrote of_rates_dump.json (OFRL_DUMP_RATES=1, E7 per-reaction)"
            << nl;

        if (Foam::getEnv("OFRL_DUMP_RATES_ONLY") == "1")
        {
            // Clean exit so OFstream buffers are flushed (FatalError skips dtors).
            std::exit(0);
        }
    }

    // E14: clear chemistry-substep stash before StandardChemistryModel::solve
    ofRlInvariants::beginWindow();

    // Snapshot Y before RR is applied (for ΔY_applied vs ΔY_RR)
    if (ofRlInvariants::enabled())
    {
        e14Ybefore.setSize(Y.size());
        forAll(Y, i)
        {
            e14Ybefore[i] = Y[i][0];
        }
    }

    dtChem = chemistry.solve(runTime.deltaTValue());

    // Qdot [W/m3] / rho → [J/(kg·s)]; integratedHeat accumulates [J/kg]
    // (name Qdot kept for stock output.H)
    Qdot = chemistry.Qdot()()[0]/rho[0];
    QdotPerMass = Qdot;
    dIntegratedHeat = Qdot*runTime.deltaTValue();
    integratedHeat += dIntegratedHeat;

    // Hook B: RR / Qdot ledger fields for e14 CSV (written after YEqn)
    if (ofRlInvariants::enabled())
    {
        e14SumRR = 0;
        e14NegHcDeltaYRR = 0;
        e14MaxAbsDeltaYRR = 0;
        e14MaxAbsDeltaYRRName = word::null;
        const scalar dt = runTime.deltaTValue();
        const scalar rhoi = rho[0];
        e14DeltaYRR.setSize(Y.size());
        forAll(Y, i)
        {
            const scalar RRi = chemistry.RR(i)[0];
            e14SumRR += RRi;
            const scalar dY = RRi*dt/rhoi;
            e14DeltaYRR[i] = dY;
            e14NegHcDeltaYRR -= specieData[i].Hc()*dY;
            if (mag(dY) > e14MaxAbsDeltaYRR)
            {
                e14MaxAbsDeltaYRR = mag(dY);
                e14MaxAbsDeltaYRRName = Y[i].name();
            }
        }
    }
}
