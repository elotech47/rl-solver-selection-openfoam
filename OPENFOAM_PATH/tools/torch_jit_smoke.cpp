// Minimal LibTorch JIT load (no OpenFOAM). Build:
//   g++ -O2 -std=c++17 -D_GLIBCXX_USE_CXX11_ABI=1 \
//     -I$LIBTORCH_DIR/include -I$LIBTORCH_DIR/include/torch/csrc/api/include \
//     tools/torch_jit_smoke.cpp -o opt/bin/torch_jit_smoke \
//     -L$LIBTORCH_DIR/lib -Wl,-rpath,$LIBTORCH_DIR/lib \
//     -ltorch -ltorch_cpu -lc10
#include <torch/script.h>
#include <iostream>
#include <cstdlib>

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::cerr << "usage: torch_jit_smoke policy.ts\n";
        return 2;
    }
    try
    {
        at::globalContext().setUserEnabledMkldnn(false);
        auto m = torch::jit::load(argv[1]);
        m.eval();
        std::cout << "JIT_LOAD_OK " << argv[1] << "\n";
        return 0;
    }
    catch (const std::exception& e)
    {
        std::cerr << "JIT_LOAD_FAIL " << e.what() << "\n";
        return 1;
    }
}
