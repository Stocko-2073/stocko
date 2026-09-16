#pragma once
#include <cmath>
#include <cstdint>

namespace BedMesh {
constexpr int columns[] = {1, 17, 34}, rows[] = {0, 12, 25};
constexpr uint16_t complete = 0x1ff;
// Nonuniform cells: 16/17 column intervals, 12/13 row intervals.
void sample(const int64_t points[9][3], double col, double row, double out[3]) {
  const int c = col <= 17 ? 0 : 1, r = row <= 12 ? 0 : 1;
  const double u = (col-columns[c])/(columns[c+1]-columns[c]);
  const double v = (row-rows[r])/(rows[r+1]-rows[r]);
  for (int a=0; a<3; ++a) {
    const double top = points[r*3+c][a]*(1-u)+points[r*3+c+1][a]*u;
    const double bottom = points[(r+1)*3+c][a]*(1-u)+points[(r+1)*3+c+1][a]*u;
    out[a] = top*(1-v)+bottom*v;
  }
}
// Invert the XY surface for readout and relative height compensation.
bool locate(const int64_t points[9][3], double x, double y, double &col, double &row) {
  col=1+x/254; row=-y/254;
  for (int i=0; i<16; ++i) {
    double p[3], pc[3], pr[3];
    sample(points,col,row,p); sample(points,col+0.001,row,pc); sample(points,col,row+0.001,pr);
    const double dx=x-p[0], dy=y-p[1];
    if (std::abs(dx)+std::abs(dy)<0.001) return true;
    const double a=(pc[0]-p[0])/0.001, b=(pr[0]-p[0])/0.001;
    const double c=(pc[1]-p[1])/0.001, d=(pr[1]-p[1])/0.001, det=a*d-b*c;
    if (std::abs(det)<1) return false;
    col+=(dx*d-b*dy)/det; row+=(a*dy-dx*c)/det;
  }
  return false;
}
int64_t rounded(double n) { return int64_t(std::floor(n+0.5)); }
// Reject folded or reversed cells. A bilinear cell's Jacobian is affine,
// so checking its four corners covers its whole interior.
bool valid(const int64_t points[9][3]) {
  for (int a=0; a<3; ++a) if (points[0][a]) return false;
  for (int r=0; r<2; ++r) for (int c=0; c<2; ++c)
    for (int v=0; v<2; ++v) for (int u=0; u<2; ++u) {
      const auto *left=points[(r+v)*3+c], *right=points[(r+v)*3+c+1];
      const auto *top=points[r*3+c+u], *bottom=points[(r+1)*3+c+u];
      const double dx=right[0]-left[0], dy=right[1]-left[1];
      const double ex=bottom[0]-top[0], ey=bottom[1]-top[1];
      if (dx<=0 || ey>=0 || dx*ey-dy*ex>=-1) return false;
    }
  return true;
}
}
