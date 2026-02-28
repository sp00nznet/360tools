// Minimal tool to extract the decrypted+decompressed PE image from an XEX2 file.
// Links against XenonRecomp's XenonUtils library.
// Usage: dump_pe <input.xex> <output.bin>

#include <cstdio>
#include <cstdlib>
#include <vector>
#include "xex.h"
#include "image.h"

int main(int argc, char* argv[])
{
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <input.xex> <output.bin>\n", argv[0]);
        return 1;
    }

    // Read XEX file
    FILE* f = fopen(argv[1], "rb");
    if (!f) {
        fprintf(stderr, "Failed to open: %s\n", argv[1]);
        return 1;
    }
    fseek(f, 0, SEEK_END);
    size_t sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> xex(sz);
    fread(xex.data(), 1, sz, f);
    fclose(f);

    // Load and decrypt/decompress
    Image img = Xex2LoadImage(xex.data(), xex.size());
    if (!img.data || img.size == 0) {
        fprintf(stderr, "Failed to load XEX image\n");
        return 1;
    }

    printf("PE image: %u bytes, base=0x%zX, entry=0x%zX\n",
           img.size, img.base, img.entry_point);
    printf("Sections: %zu\n", img.sections.size());
    for (const auto& sec : img.sections) {
        printf("  %-8s VA=0x%08zX Size=0x%06zX\n",
               sec.name.c_str(), sec.base, sec.size);
    }

    // Write raw PE image
    FILE* out = fopen(argv[2], "wb");
    if (!out) {
        fprintf(stderr, "Failed to open output: %s\n", argv[2]);
        return 1;
    }
    fwrite(img.data.get(), 1, img.size, out);
    fclose(out);

    printf("Wrote %u bytes to %s\n", img.size, argv[2]);
    return 0;
}
