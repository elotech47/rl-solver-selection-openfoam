// Mass-weighted h→T Newton, consistent with h0 = Σ Yi·Hs_i in
// readInitialConditions.H. The stock hePsiThermo::correct() THE path uses
// JANAF-coefficient-blended cellMixture, which for Luo n-dodecane runaway
// yields collapsing/negative cp (E8 H6).
//
// Strategy: invert T from Σ Yi·Hs_i = f, then set he to the *blended*
// Hs(T) so THE is a numerical no-op, and call thermo.correct() only to
// refresh psi/mu/alpha from the new T.
{
    scalar& Tcell = thermo.T().ref()[0];
    const scalar pCell = p[0];
    const scalar fTarget = h[0];

    scalar Test = Tcell;
    scalar Tnew = Test;
    // Match species::thermo::T defaults (tol_ = 1e-4 relative, maxIter_ = 100)
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
            const scalar Yi = Y[i][0];
            hs += Yi*composition.Hs(i, pCell, Test);
            cp += Yi*composition.Cp(i, pCell, Test);
        }

        if (mag(cp) < SMALL)
        {
            FatalErrorInFunction
                << "Mass-weighted cp ~ 0 at T=" << Test
                << " hs=" << hs << " f=" << fTarget
                << abort(FatalError);
        }

        Tnew = Test - (hs - fTarget)/cp;
        Tnew = min(max(Tnew, scalar(200)), scalar(5000));

        if (++iter > maxIter)
        {
            FatalErrorInFunction
                << "Mass-weighted T Newton exceeded " << maxIter
                << " iterations; T0=" << thermo.T()[0]
                << " old T=" << Test << " new T=" << Tnew
                << " f=" << fTarget << " hs=" << hs << " cp=" << cp
                << abort(FatalError);
        }
    } while (mag(Tnew - Test) > Ttol);

    Tcell = Tnew;

    // Blended Hs at the mass-weighted T → THE residual is ~0 (no-op),
    // while correct() still refreshes psi from the EOS at Tcell.
    {
        gasHThermoPhysics mixBlend(Y[0][0]*specieData[0]);
        for (label i = 1; i < Y.size(); ++i)
        {
            mixBlend += Y[i][0]*specieData[i];
        }
        h[0] = mixBlend.Hs(pCell, Tcell);
    }

    thermo.correct();

    // Restore the energy-equation target for field bookkeeping.
    h[0] = fTarget;
}
