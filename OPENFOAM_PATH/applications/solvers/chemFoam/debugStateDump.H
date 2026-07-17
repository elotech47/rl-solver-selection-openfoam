// E8 state dump — active only when OFRL_DEBUG_STATE=1 (env) or
// debugState true in system/controlDict. Log only; never clip/alter state.
{
    const Foam::string dbgEnv = Foam::getEnv("OFRL_DEBUG_STATE");
    const bool debugState =
        (dbgEnv == "1")
     || runTime.controlDict().lookupOrDefault("debugState", false);

    if (!debugState)
    {
        // Bit-identical path: fall straight through to thermo.correct()
    }
    else
    {
        const scalar Tprev = thermo.T()[0];
        const scalar pCell = p[0];
        const scalar dt = runTime.deltaTValue();

        scalar sumY = 0;
        scalar minY = GREAT;
        label minYi = 0;

        scalar negV[5] = {GREAT, GREAT, GREAT, GREAT, GREAT};
        label negI[5] = {0, 0, 0, 0, 0};

        forAll(Y, i)
        {
            const scalar Yi = Y[i][0];
            sumY += Yi;
            if (Yi < minY)
            {
                minY = Yi;
                minYi = i;
            }
            for (int k = 0; k < 5; ++k)
            {
                if (Yi < negV[k])
                {
                    for (int m = 4; m > k; --m)
                    {
                        negV[m] = negV[m-1];
                        negI[m] = negI[m-1];
                    }
                    negV[k] = Yi;
                    negI[k] = i;
                    break;
                }
            }
        }

        // OF cellMixture path (NASA-coeff blend) — what THE()/correct() uses
        gasHThermoPhysics mixCell(Y[0][0]*specieData[0]);
        for (label i = 1; i < Y.size(); ++i)
        {
            mixCell += Y[i][0]*specieData[i];
        }
        const scalar hsCell = mixCell.Hs(pCell, Tprev);
        const scalar cpCell = mixCell.Cp(pCell, Tprev);

        // Mass-weighted Σ Yi·Hs_i (Cantera-like; diagnostic)
        scalar hsSum = 0;
        scalar cpSum = 0;
        forAll(Y, i)
        {
            const scalar Yi = Y[i][0];
            hsSum += Yi*composition.Hs(i, pCell, Tprev);
            cpSum += Yi*composition.Cp(i, pCell, Tprev);
        }

        const scalar fTarget =
            (constProp == "volume")
          ? (u0 + p[0]/rho[0] + integratedHeat)
          : (h0 + integratedHeat);

        scalar sumRR = 0;
        forAll(Y, i)
        {
            sumRR += chemistry.RR(i)[0];
        }
        const scalar rhoFromC = rhoChemUsed + dt*sumRR;
        tmp<volScalarField> trhoDbg(thermo.rho());
        const scalar rhoThermoNow = trhoDbg()[0];

        const scalar R2sum = mag(hsSum - fTarget);
        const scalar R2cell = mag(hsCell - fTarget);

        if (!e8StateCsv.valid())
        {
            e8StateCsv.reset(new OFstream(args.path()/"e8_state.csv"));
            *e8StateCsv
                << "#t,Tprev,sumY,minY,minYname,hsSum,cpSum,hsCell,cpCell,f,"
                << "R2sum,R2cell,rhoChem,rhoThermo,rhoFromC,"
                << "dQdot_dt_over_rho,dIntegratedHeat,"
                << "neg0,neg0Y,neg1,neg1Y,neg2,neg2Y,neg3,neg3Y,neg4,neg4Y"
                << nl;
        }

        *e8StateCsv
            << runTime.value() << ','
            << Tprev << ','
            << sumY << ','
            << minY << ','
            << Y[minYi].name() << ','
            << hsSum << ','
            << cpSum << ','
            << hsCell << ','
            << cpCell << ','
            << fTarget << ','
            << R2sum << ','
            << R2cell << ','
            << rhoChemUsed << ','
            << rhoThermoNow << ','
            << rhoFromC << ','
            << QdotPerMass*dt << ','
            << dIntegratedHeat << ','
            << Y[negI[0]].name() << ',' << negV[0] << ','
            << Y[negI[1]].name() << ',' << negV[1] << ','
            << Y[negI[2]].name() << ',' << negV[2] << ','
            << Y[negI[3]].name() << ',' << negV[3] << ','
            << Y[negI[4]].name() << ',' << negV[4]
            << nl;
        e8StateCsv().flush();

        // Newton probe with cellMixture (matches correct())
        const scalar dTnewton =
            (mag(cpCell) > SMALL) ? (hsCell - fTarget)/cpCell : 1e30;
        const scalar TnewProbe = Tprev - dTnewton;
        const bool crashLikely =
            (minY < -1e-4)
         || (TnewProbe < 200) || (TnewProbe > 5000)
         || (R2cell > 1e5 && Tprev > 1200)
         || (R2sum > 1e5 && Tprev > 1200);

        const bool dumpNow =
            crashLikely
         && (
                (!e8CrashDumped && (R2cell > 1e5 || R2sum > 1e5))
             || (e8CrashDumped && R2sum > 2.5e5 && Tprev > 1800 && !e8LateDumped)
            );

        if (dumpNow)
        {
            if (R2sum > 2.5e5 && Tprev > 1800) e8LateDumped = true;
            e8CrashDumped = true;
            Info<< "OFRL_DEBUG_STATE: dump t=" << runTime.value()
                << " Tprev=" << Tprev
                << " TnewProbe(cell)=" << TnewProbe
                << " minY=" << minY << " (" << Y[minYi].name() << ")"
                << " sumY=" << sumY
                << " hsSum=" << hsSum << " hsCell=" << hsCell
                << " cpSum=" << cpSum << " cpCell=" << cpCell
                << " f=" << fTarget
                << " R2sum=" << R2sum << " R2cell=" << R2cell
                << nl;

            OFstream crashY(args.path()/"e8_crash_state.dat");
            crashY<< "# species Y  t=" << runTime.value()
                  << " Tprev=" << Tprev << nl;
            crashY.precision(17);
            forAll(Y, i)
            {
                crashY<< Y[i].name() << token::SPACE << Y[i][0] << nl;
            }
            crashY.flush();

            OFstream crashHs(args.path()/"e8_crash_hs_cp.dat");
            crashHs<< "# T  hsSum  cpSum  hsCell  cpCell  f=" << fTarget << nl;
            const scalar Ts[8] = {800,1200,1500,1638,1841,2200,2600,3000};
            for (label ti = 0; ti < 8; ++ti)
            {
                const scalar Tgrid = Ts[ti];
                scalar hsS = 0, cpS = 0;
                forAll(Y, i)
                {
                    const scalar Yi = Y[i][0];
                    hsS += Yi*composition.Hs(i, pCell, Tgrid);
                    cpS += Yi*composition.Cp(i, pCell, Tgrid);
                }
                gasHThermoPhysics mix(Y[0][0]*specieData[0]);
                for (label i = 1; i < Y.size(); ++i)
                {
                    mix += Y[i][0]*specieData[i];
                }
                crashHs<< Tgrid << ' ' << hsS << ' ' << cpS
                       << ' ' << mix.Hs(pCell, Tgrid)
                       << ' ' << mix.Cp(pCell, Tgrid) << nl;
            }
            crashHs.flush();

            Info<< "OFRL_DEBUG_STATE: wrote e8_crash_state.dat / "
                << "e8_crash_hs_cp.dat" << nl;
        }
    }
}
