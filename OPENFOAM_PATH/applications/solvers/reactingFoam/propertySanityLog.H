// E12.2 property-sanity log (OFRL_PROP_SANITY=1 or controlDict propSanity).
// Every step: min/max T, cp (thermo), alphaEff (+ thermo.alpha for laminar check).
// Every propSanityInterval steps: max |cpBlend−ΣYi·cpi|/cpSum (Option R → ~round-off).
//
// alphaEff resolution (E17 preflight): probe uses turbulence->alphaEff(), the same
// accessor as EEqn.H. Under simulationType laminar + ThermalDiffusivity this is
// transport_.alphahe() [kg/m/s]. Observed "alphaEff 0 0" in early e12 logs was
// NOT a wrong-field bug — for laminar, alphat=0 and alphahe can print as 0 when
// the enthalpy diffusivity field has not been corrected yet that step, or is
// numerically ~0 in Info precision. We also log thermo.alpha() (temperature
// diffusivity) so a genuine molecular transport signal is visible.
{
    const Foam::string propEnv = Foam::getEnv("OFRL_PROP_SANITY");
    const bool propSanity =
        (propEnv == "1")
     || runTime.controlDict().lookupOrDefault("propSanity", false);

    if (propSanity)
    {
        const label interval =
            runTime.controlDict().lookupOrDefault("propSanityInterval", 50);

        const volScalarField& Tfld = thermo.T();
        tmp<volScalarField> tcp = thermo.Cp();
        const volScalarField& cpFld = tcp();
        tmp<volScalarField> talpha = turbulence->alphaEff();
        const volScalarField& alphaEff = talpha();
        tmp<volScalarField> talphaMol = thermo.alpha();
        const volScalarField& alphaMol = talphaMol();

        const scalar cpMin = gMin(cpFld);
        const scalar cpMax = gMax(cpFld);
        const scalar alphaMin = gMin(alphaEff);
        const scalar alphaMax = gMax(alphaEff);
        const scalar alphaMolMin = gMin(alphaMol);
        const scalar alphaMolMax = gMax(alphaMol);
        const scalar Tmin = gMin(Tfld);
        const scalar Tmax = gMax(Tfld);

        scalar maxRelBlend = -1;
        label worstCell = -1;

        static label propStep = 0;
        const bool doBlend = (propStep % interval == 0);
        ++propStep;

        if (doBlend)
        {
            const reactingMixture<gasHThermoPhysics>& reactMix =
                dynamic_cast<const reactingMixture<gasHThermoPhysics>&>(thermo);
            const PtrList<gasHThermoPhysics>& specieData = reactMix.speciesData();
            const volScalarField& pfld = thermo.p();
            maxRelBlend = 0;

            forAll(Tfld, celli)
            {
                const scalar pCell = pfld[celli];
                const scalar Tcell = Tfld[celli];

                gasHThermoPhysics mixCell(Y[0][celli]*specieData[0]);
                for (label i = 1; i < Y.size(); ++i)
                {
                    mixCell += Y[i][celli]*specieData[i];
                }
                const scalar cpCell = mixCell.Cp(pCell, Tcell);

                scalar cpSum = 0;
                forAll(Y, i)
                {
                    cpSum += Y[i][celli]*composition.Cp(i, pCell, Tcell);
                }

                if (mag(cpSum) > SMALL)
                {
                    const scalar rel = mag(cpCell - cpSum)/mag(cpSum);
                    if (rel > maxRelBlend)
                    {
                        maxRelBlend = rel;
                        worstCell = celli;
                    }
                }
            }
        }

        Info<< "propSanity: T " << Tmin << " " << Tmax
            << "  cp " << cpMin << " " << cpMax
            << "  alphaEff " << alphaMin << " " << alphaMax
            << "  alpha " << alphaMolMin << " " << alphaMolMax;
        if (doBlend)
        {
            Info<< "  max|cpBlend-cpSum|/cpSum = " << maxRelBlend
                << " (cell " << worstCell << ")";
        }
        Info<< endl;

        static autoPtr<OFstream> propCsv;
        if (!propCsv.valid())
        {
            propCsv.reset
            (
                new OFstream(runTime.path()/"e12_prop_sanity.csv")
            );
            *propCsv
                << "#t,Tmin,Tmax,cpMin,cpMax,alphaEffMin,alphaEffMax,alphaMin,alphaMax,maxRelBlend,worstCell"
                << nl;
        }
        *propCsv
            << runTime.value() << ','
            << Tmin << ',' << Tmax << ','
            << cpMin << ',' << cpMax << ','
            << alphaMin << ',' << alphaMax << ','
            << alphaMolMin << ',' << alphaMolMax << ','
            << maxRelBlend << ','
            << worstCell
            << nl;
    }
}
