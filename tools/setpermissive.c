/*
 * setpermissive - load a binary SELinux policy, mark every type "permissive",
 * and write it back. Used to make the TCL Flip 4's precompiled_sepolicy fully
 * permissive offline (no Magisk), then re-sealed under AVB with the test key.
 *
 * Build (Linux, libsepol-dev): cc -O2 -o setpermissive setpermissive.c -lsepol
 * Usage: ./setpermissive <in_policy> <out_policy>
 */
#include <stdio.h>
#include <stdlib.h>
#include <sepol/policydb/policydb.h>
#include <sepol/policydb/ebitmap.h>

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s <in_policy> <out_policy>\n", argv[0]);
        return 2;
    }

    FILE *in = fopen(argv[1], "rb");
    if (!in) { perror("open input"); return 1; }

    struct policy_file pf;
    policy_file_init(&pf);
    pf.type = PF_USE_STDIO;
    pf.fp = in;

    policydb_t pol;
    if (policydb_init(&pol)) { fprintf(stderr, "policydb_init failed\n"); return 1; }
    if (policydb_read(&pol, &pf, 0)) { fprintf(stderr, "policydb_read failed\n"); return 1; }
    fclose(in);

    unsigned int made = 0;
    for (uint32_t v = 1; v <= pol.p_types.nprim; v++) {
        type_datum_t *t = pol.type_val_to_struct[v - 1];
        if (!t || t->flavor != TYPE_TYPE)
            continue;               /* skip attributes and aliases */
        if (ebitmap_set_bit(&pol.permissive_map, v, 1)) {
            fprintf(stderr, "ebitmap_set_bit failed for type %u\n", v);
            return 1;
        }
        made++;
    }

    FILE *out = fopen(argv[2], "wb");
    if (!out) { perror("open output"); return 1; }
    pf.fp = out;
    if (policydb_write(&pol, &pf)) { fprintf(stderr, "policydb_write failed\n"); return 1; }
    fclose(out);

    policydb_destroy(&pol);
    fprintf(stderr, "made %u types permissive\n", made);
    return 0;
}
