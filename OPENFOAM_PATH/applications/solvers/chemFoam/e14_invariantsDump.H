// E14 Hook D — append energy ledger CSV (OFRL_DEBUG_INVARIANTS=1 only)
{
    if (ofRlInvariants::enabled())
    {
        const scalar Tprev = thermo.T()[0];
        const scalar pCell = p[0];
        const scalar fTarget =
            (constProp == "volume")
          ? (u0 + p[0]/rho[0] + integratedHeat)
          : (h0 + integratedHeat);

        gasHThermoPhysics mixCell(Y[0][0]*specieData[0]);
        for (label i = 1; i < Y.size(); ++i)
        {
            mixCell += Y[i][0]*specieData[i];
        }
        const scalar hsCell = mixCell.Hs(pCell, Tprev);
        const scalar cpCell = mixCell.Cp(pCell, Tprev);
        const scalar dTnewton =
            (mag(cpCell) > SMALL) ? (hsCell - fTarget)/cpCell : 1e30;
        const scalar TnewtonProbe = Tprev - dTnewton;

        const scalar Tint =
            ofRlInvariants::valid() ? ofRlInvariants::Tint() : -1;
        const scalar T0ode =
            ofRlInvariants::valid() ? ofRlInvariants::T0() : -1;
        const label nSub =
            ofRlInvariants::valid() ? ofRlInvariants::nSub() : 0;

        if (!e14InvCsv.valid())
        {
            e14InvCsv.reset(new OFstream(args.path()/"e14_invariants.csv"));
            *e14InvCsv
                << "#t,dt,rho,T_cell,T0_ode,T_int,T_newton_probe,nSub,"
                << "sumRR,Qdot_per_mass,dIntegratedHeat,"
                << "negHc_dY_RR,negHc_dY_applied,negHc_dY_int,"
                << "maxAbs_dY_RR,maxAbs_dY_RR_name,"
                << "maxAbs_dY_diff,maxAbs_dY_diff_name"
                << nl;
        }

        *e14InvCsv
            << runTime.value() << ','
            << runTime.deltaTValue() << ','
            << rhoChemUsed << ','
            << Tprev << ','
            << T0ode << ','
            << Tint << ','
            << TnewtonProbe << ','
            << nSub << ','
            << e14SumRR << ','
            << QdotPerMass << ','
            << dIntegratedHeat << ','
            << e14NegHcDeltaYRR << ','
            << e14NegHcDeltaYApplied << ','
            << e14NegHcDeltaYInt << ','
            << e14MaxAbsDeltaYRR << ','
            << e14MaxAbsDeltaYRRName << ','
            << e14MaxAbsDeltaYDiff << ','
            << e14MaxAbsDeltaYDiffName
            << nl;
        e14InvCsv().flush();

        // E14.5: full Y for elemental-drift audit (CHEMEQ2 atom conservation)
        if (!e14YCsv.valid())
        {
            e14YCsv.reset(new OFstream(args.path()/"e14_Y.csv"));
            *e14YCsv << "#t,sumY";
            forAll(Y, i)
            {
                *e14YCsv << ',' << Y[i].name();
            }
            *e14YCsv << nl;
        }
        scalar sumYdump = 0;
        forAll(Y, i)
        {
            sumYdump += Y[i][0];
        }
        *e14YCsv << runTime.value() << ',' << sumYdump;
        forAll(Y, i)
        {
            *e14YCsv << ',' << Y[i][0];
        }
        *e14YCsv << nl;
        e14YCsv().flush();
    }
}
