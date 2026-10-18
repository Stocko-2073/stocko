# stocko

## GitHub account

This repo is `Stocko-2073/stocko`. Always use the **Stocko-2073** account with
`gh`; it is the only account with write access here. If more than one account
is logged in, check `gh auth status` and run `gh auth switch --user Stocko-2073`
before doing anything with PRs, issues or releases.

Git pushes use the `stocko-git` SSH alias from `~/.ssh/config`; `gh` resolves
that alias to github.com on its own, so commands like `gh pr view` work from
inside the checkout without `--repo`.

## CAD

OpenSCAD+BOSL2 models in this repo follow
[CAD_STYLE_GUIDE.md](CAD_STYLE_GUIDE.md). Read it before writing or editing a
`.scad` file.

`openscad` is Stocko's custom build for AI agents. Run `openscad --help` to see
the extra tools it adds.

For a printed part's mass, center of mass or inertia, run
`tools/print_mass.py model.scad` (see `--help`). It slices each `// print` line
with Bambu Studio and sums the G-code, so walls, infill and print orientation
count; the CAD solid's mass and centroid are not what prints.
