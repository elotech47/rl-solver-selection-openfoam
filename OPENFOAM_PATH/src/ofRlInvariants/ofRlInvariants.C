#include "ofRlInvariants.H"
#include "OSspecific.H"

namespace Foam
{
namespace ofRlInvariants
{
namespace
{

bool enabled_ = false;
bool envChecked_ = false;
bool valid_ = false;
label nSub_ = 0;
scalar T0_ = 0;
scalar Tint_ = 0;
scalar deltaTChem_ = 0;
scalarField c0_;
scalarField cEnd_;

} // namespace


bool enabled()
{
    if (!envChecked_)
    {
        enabled_ = (Foam::getEnv("OFRL_DEBUG_INVARIANTS") == "1");
        envChecked_ = true;
    }
    return enabled_;
}


void beginWindow()
{
    if (!enabled())
    {
        return;
    }
    nSub_ = 0;
    valid_ = false;
}


void recordSolve
(
    const scalar T0in,
    const scalar TintIn,
    const scalar deltaTChemIn,
    const scalarField& c0In,
    const scalarField& cEndIn
)
{
    if (!enabled())
    {
        return;
    }
    if (nSub_ == 0)
    {
        T0_ = T0in;
        c0_ = c0In;
    }
    Tint_ = TintIn;
    deltaTChem_ = deltaTChemIn;
    cEnd_ = cEndIn;
    ++nSub_;
    valid_ = true;
}


bool valid() { return valid_; }
label nSub() { return nSub_; }
scalar T0() { return T0_; }
scalar Tint() { return Tint_; }
scalar deltaTChem() { return deltaTChem_; }
const scalarField& c0() { return c0_; }
const scalarField& cEnd() { return cEnd_; }

} // namespace ofRlInvariants
} // namespace Foam
