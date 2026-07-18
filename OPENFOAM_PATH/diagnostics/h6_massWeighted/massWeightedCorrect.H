// Mass-weighted h→T for reactingFoam (H6 fix).
// After EEqn solves he, invert T from Σ Yi·Hs_i(he) instead of
// cellMixture JANAF blending in thermo.correct()/THE.
// Temporarily set he to blended Hs(T) so THE is a no-op; restore he after.
{
    volScalarField& Tmw = thermo.T();
    volScalarField& heMw = thermo.he();
    const volScalarField& pMw = thermo.p();

    const reactingMixture<gasHThermoPhysics>& reactMix =
        dynamic_cast<const reactingMixture<gasHThermoPhysics>&>(thermo);

    // Snapshot of EEqn he (conserved energy) before THE no-op trick
    scalarField heSaved(heMw.primitiveField());

    forAll(Tmw, celli)
    {
        const scalar pCell = pMw[celli];
        const scalar fTarget = heSaved[celli];
        scalar Test = Tmw[celli];
        scalar Tnew = Test;
        const scalar Ttol = max(Test*1e-4, SMALL);
        int iter = 0;
        const int maxIter = 100;

        do
        {
            Test = Tnew;
            scalar hs = 0;
            scalar cp = 0;
            forAll(Y, i)
            {
                const scalar Yi = Y[i][celli];
                hs += Yi*composition.Hs(i, pCell, Test);
                cp += Yi*composition.Cp(i, pCell, Test);
            }

            if (mag(cp) < SMALL)
            {
                FatalErrorInFunction
                    << "Mass-weighted cp ~ 0 at cell " << celli
                    << " T=" << Test << " hs=" << hs << " he=" << fTarget
                    << abort(FatalError);
            }

            Tnew = Test - (hs - fTarget)/cp;
            Tnew = min(max(Tnew, scalar(200)), scalar(5000));

            if (++iter > maxIter)
            {
                FatalErrorInFunction
                    << "Mass-weighted T Newton exceeded " << maxIter
                    << " at cell " << celli
                    << " T0=" << Tmw[celli]
                    << " old T=" << Test << " new T=" << Tnew
                    << " he=" << fTarget << " hs=" << hs << " cp=" << cp
                    << abort(FatalError);
            }
        } while (mag(Tnew - Test) > Ttol);

        Tmw[celli] = Tnew;

        // Blended Hs at mass-weighted T → THE residual ~ 0 inside correct()
        gasHThermoPhysics mixBlend(Y[0][celli]*reactMix.speciesData()[0]);
        for (label i = 1; i < Y.size(); ++i)
        {
            mixBlend += Y[i][celli]*reactMix.speciesData()[i];
        }
        heMw[celli] = mixBlend.Hs(pCell, Tnew);
    }

    thermo.correct();

    // Restore EEqn energy field
    heMw.primitiveFieldRef() = heSaved;
}
