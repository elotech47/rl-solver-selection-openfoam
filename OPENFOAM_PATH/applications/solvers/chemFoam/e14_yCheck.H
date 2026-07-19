// E14 Hook C — ΔY_applied vs ΔY_RR (OFRL_DEBUG_INVARIANTS=1 only)
{
    if (ofRlInvariants::enabled())
    {
        e14MaxAbsDeltaYDiff = 0;
        e14MaxAbsDeltaYDiffName = word::null;
        e14NegHcDeltaYApplied = 0;
        forAll(Y, i)
        {
            const scalar dYapp = Y[i][0] - e14Ybefore[i];
            e14NegHcDeltaYApplied -= specieData[i].Hc()*dYapp;
            const scalar diff = mag(dYapp - e14DeltaYRR[i]);
            if (diff > e14MaxAbsDeltaYDiff)
            {
                e14MaxAbsDeltaYDiff = diff;
                e14MaxAbsDeltaYDiffName = Y[i].name();
            }
        }

        // −Σ Hc·ΔY from integrator stash (window c0→cEnd), mass basis
        e14NegHcDeltaYInt = 0;
        if (ofRlInvariants::valid())
        {
            const scalarField& c0s = ofRlInvariants::c0();
            const scalarField& cEs = ofRlInvariants::cEnd();
            const label n = min(c0s.size(), Y.size());
            for (label i = 0; i < n; ++i)
            {
                const scalar dY =
                    (cEs[i] - c0s[i])*specieData[i].W()/rhoChemUsed;
                e14NegHcDeltaYInt -= specieData[i].Hc()*dY;
            }
        }
    }
}
