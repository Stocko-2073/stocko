#include <cassert>
#include <iostream>
#include "../xyza/xyza.ino"

int action(const char *op, const char *axis="", const char *pulses="") {
  WebControl::server.args={{"op",op},{"axis",axis},{"pulses",pulses},{"client","test-browser-0001"}};
  WebControl::action();
  return WebControl::server.code;
}
void run() {
  int iterations=0;
  while (!WebControl::idle() && iterations++ < 30000) {
    webHeartbeat=millis(); loop();
  }
  assert(WebControl::idle());
}
int meshAction(const char *op,int point=0) {
  WebControl::server.args={{"op",op},{"point",std::to_string(point)},{"client","test-browser-0001"}};
  WebControl::action(); return WebControl::server.code;
}
void testMesh() {
  action("stop");
  assert(action("home")==200);
  // Upgrade the actual v2 prefix without losing the existing span/home.
  {
    auto &blob=Positions::preferences.blob;
    blob.resize(Positions::version2Size); const uint32_t v2=2; memcpy(blob.data(),&v2,sizeof(v2));
    Positions::begin();
    assert(Positions::saved.version==3 && Positions::saved.homeSet && Positions::saved.spanSet && !Positions::saved.meshSet);
    assert(!Positions::saved.calibrating && !Positions::saved.draftMask);
    assert(action("confirm")==200);
  }
  assert(action("mesh-start")==200 && Positions::saved.draftMask==1);
  assert(action("mesh-apply")==409 && !Positions::saved.meshSet);
  assert(meshAction("mesh-save",9)==400 && meshAction("mesh-save",0)==409);
  emitted[0]=Positions::saved.home[0]+4064; emitted[3]=Positions::saved.home[3]+1001;
  assert(meshAction("mesh-save",1)==409 && Positions::saved.draftMask==1);
  int64_t mesh[9][3];
  // Skewed XY and a hump at M17, deliberately non-planar in all axes.
  for (int r=0;r<3;++r) for (int c=0;c<3;++c) {
    const int i=r*3+c;
    mesh[i][0]=(BedMesh::columns[c]-1)*254+r*c*2+(r==1?20:0);
    mesh[i][1]=-BedMesh::rows[r]*254+c*15;
    mesh[i][2]=r*40+c*15+(r==1&&c==1?100:0);
    if (!i) continue;
    emitted[0]=Positions::saved.home[0]+mesh[i][0];
    emitted[1]=Positions::saved.home[1]+mesh[i][1];
    emitted[3]=Positions::saved.home[3]+mesh[i][2];
    Positions::settled(false);
    if (i==4) {
      const auto before=Positions::saved;
      Positions::preferences.failWrite=true;
      assert(meshAction("mesh-save",i)==503 && Positions::saved.draftMask==before.draftMask);
      Positions::preferences.failWrite=false;
    }
    assert(meshAction("mesh-save",i)==200);
  }
  assert(Positions::saved.draftMask==511 && !Positions::saved.meshSet);
  // In-progress measurements survive a reboot and require re-reference.
  Positions::begin(); assert(!Positions::known && Positions::saved.draftMask==511);
  assert(action("mesh-apply")==409);
  assert(action("confirm")==200);
  Positions::preferences.failWrite=true;
  assert(action("mesh-apply")==503 && !Positions::saved.meshSet && Positions::saved.calibrating);
  Positions::preferences.failWrite=false;
  assert(action("mesh-apply")==200 && Positions::saved.meshSet && !Positions::saved.calibrating);
  assert(!memcmp(mesh,Positions::saved.mesh,sizeof(mesh)));
  assert(action("span")==409);
  WebControl::state();
  assert(WebControl::server.body.find("\"meshSet\":true")!=std::string::npos);
  assert(WebControl::server.body.find("\"mesh\":[[0,0,0]")!=std::string::npos);
  // Exact knots, cell interiors, shared seams, and inverse mapping at every hole.
  for (int r=0;r<3;++r) for (int c=0;c<3;++c) {
    double p[3]; BedMesh::sample(mesh,BedMesh::columns[c],BedMesh::rows[r],p);
    for (int a=0;a<3;++a) assert(p[a]==mesh[r*3+c][a]);
  }
  {
    double p[3]; BedMesh::sample(mesh,9,6,p);
    assert(p[0]==2042.5 && p[1]==-1516.5 && p[2]==52.5);
    BedMesh::sample(mesh,25.5,18.5,p);
    for (int a=0;a<3;++a) assert(p[a]==(mesh[4][a]+mesh[5][a]+mesh[7][a]+mesh[8][a])/4.0);
    double left[3],right[3]; BedMesh::sample(mesh,17-1e-7,12,left); BedMesh::sample(mesh,17+1e-7,12,right);
    for (int a=0;a<3;++a) assert(std::abs(left[a]-right[a])<0.001);
  }
  for (int r=0;r<26;++r) for (int c=1;c<=34;++c) {
    int64_t x,y; WebControl::holeOffset(c,r,x,y);
    double col,row; assert(BedMesh::locate(mesh,x,y,col,row));
    assert(BedMesh::rounded(col)==c && BedMesh::rounded(row)==r);
    double p[3]; BedMesh::sample(mesh,c,r,p);
    assert(WebControl::bedHeight(x,y)==BedMesh::rounded(p[2]));
  }
  auto bad=Positions::saved;
  for (int i=0;i<9;++i) bad.draft[i][0]=-mesh[i][0];
  assert(!BedMesh::valid(bad.draft));
  // From a low endpoint, clearance includes the interior hump; arrival Z
  // follows the destination bed while preserving the starting tip offset.
  assert(action("reference")==200); // Back at all three A1 coordinates.
  action("arm");
  WebControl::server.args={{"op","goto"},{"hole","Z34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200);
  assert(WebControl::target[3]==Positions::saved.home[3]+110);
  assert(WebControl::clearance==Positions::saved.home[3]+255); // M17 = 155, plus 100 lift.
  run();
  assert(emitted[0]==Positions::saved.home[0]+mesh[8][0] && emitted[1]==Positions::saved.home[1]+mesh[8][1]);
  assert(emitted[3]==Positions::saved.home[3]+mesh[8][2]);
  assert(action("jog","Z","-20")==200); run();
  WebControl::server.args={{"op","goto"},{"hole","M17"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[3]==Positions::saved.home[3]+135); // Keeps the -0.2 mm cutting depth.
  // Fractional interpolation must not accumulate depth error over a tour.
  for (const char *destination:{"G9","T25","A1","Z17","M17"}) {
    WebControl::server.args={{"op","goto"},{"hole",destination},{"client","test-browser-0001"}};
    WebControl::action(); assert(WebControl::server.code==200); run();
    assert(emitted[3]-Positions::saved.home[3]-WebControl::bedHeight(
      emitted[0]-Positions::saved.home[0],emitted[1]-Positions::saved.home[1])==-20);
  }
  // Whole-hole arrows use both XY corrections plus bed Z; fine jogs remain raw.
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200 && WebControl::travelRate==1000); run();
  int64_t x,y; WebControl::holeOffset(18,12,x,y);
  assert(emitted[0]==Positions::saved.home[0]+x && emitted[1]==Positions::saved.home[1]+y);
  const int64_t expectedZ=Positions::saved.home[3]+BedMesh::rounded(WebControl::bedHeight(x,y)-20);
  assert(emitted[3]==expectedZ);
  const int64_t z=emitted[3];
  assert(action("jog","X","10")==200); run(); assert(emitted[3]==z);
  // No extrapolated whole-hole steps beyond a mesh edge.
  assert(action("reference")==200);
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","-1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==400 && WebControl::idle());
  assert(std::abs(WebControl::bedHeight(-10000,0))<1000); // Edge-clamped Z.
  // A replacement draft never mutates the active mesh, including on cancel.
  assert(action("mesh-start")==200);
  assert(!memcmp(mesh,Positions::saved.mesh,sizeof(mesh)) && Positions::saved.meshSet);
  assert(meshAction("mesh-save",8)==409); // Still at A1, wrong region.
  assert(meshAction("mesh-go",8)==200);
  const int64_t raised=WebControl::clearance;
  assert(WebControl::target[3]==raised); run(); assert(emitted[3]==raised);
  assert(action("mesh-cancel")==200 && Positions::saved.meshSet);
  // Unknown-position re-homing and even saving a new origin preserve the shape.
  action("stop"); Positions::begin();
  assert(!Positions::known && Positions::saved.meshSet);
  emitted[0]=987; emitted[1]=-654; emitted[3]=321;
  assert(action("reference")==200 && !memcmp(mesh,Positions::saved.mesh,sizeof(mesh)));
  assert(emitted[0]==Positions::saved.home[0] && emitted[3]==Positions::saved.home[3]);
  Positions::known=false; emitted[0]=987; emitted[1]=-654; emitted[3]=321;
  assert(action("home")==200 && Positions::saved.home[0]==987 && Positions::saved.home[3]==321);
  Positions::begin(); assert(Positions::saved.meshSet && !memcmp(mesh,Positions::saved.mesh,sizeof(mesh)));
  assert(action("confirm")==200);
  action("arm");
  WebControl::server.args={{"op","goto"},{"hole","Z34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==987+mesh[8][0] && emitted[1]==-654+mesh[8][1] && emitted[3]==321+mesh[8][2]);
  assert(action("go-home")==200 && WebControl::clearance==321+255); run();
  assert(emitted[0]==987 && emitted[1]==-654 && emitted[3]==321);
  assert(action("mesh-start")==200 && action("home")==200 && !Positions::saved.calibrating);
  Positions::preferences.failWrite=true;
  assert(action("mesh-clear")==503 && Positions::saved.meshSet);
  Positions::preferences.failWrite=false;
  assert(action("mesh-clear")==200 && !Positions::saved.meshSet && Positions::saved.spanSet);
}
int cutAction(const char *depth="1", const char *rpm="60", const char *feed="2", const char *op="cut", const char *accel="75", const char *holes="") {
  WebControl::server.args={{"op",op},{"depth",depth},{"rpm",rpm},{"feed",feed},{"accel",accel},{"holes",holes},{"client","test-browser-0001"}};
  WebControl::action(); return WebControl::server.code;
}
int batchAction(const char *holes) { return cutAction("0.1","240","20","cut-all","750",holes); }
void testBatch() {
  action("stop"); action("home"); action("arm");
  int64_t initial[4]; Positions::snapshot(initial);
  const int writes=CutSettings::preferences.writes;
  for (const char *bad : {"", " ", "A1,N35", "A1,AA1", "A1,Z0", ",A1", "A1,", "A1,,B2", "A 1", "A1 B2"}) {
    assert(batchAction(bad)==400 && WebControl::idle() && !batchRunning);
    for (int m=0;m<4;++m) assert(emitted[m]==initial[m]);
    assert(CutSettings::preferences.writes==writes);
  }
  WebControl::BatchHole parsed[WebControl::maxBatchHoles]; size_t count; char error[128];
  std::string full="A1";
  for (size_t i=1;i<WebControl::maxBatchHoles;++i) full+=",Z34";
  assert(WebControl::parseBatch(full.c_str(),full.size(),parsed,count,error,sizeof(error)) && count==884);
  full+=",B2";
  assert(!WebControl::parseBatch(full.c_str(),full.size(),parsed,count,error,sizeof(error)));
  full=std::string(8193,' ');
  assert(!WebControl::parseBatch(full.c_str(),full.size(),parsed,count,error,sizeof(error)));
  const char nul[]={'A','1',0,',','B','2'};
  assert(!WebControl::parseBatch(nul,sizeof(nul),parsed,count,error,sizeof(error)));
  Positions::known=false; assert(batchAction("A1")==409); Positions::known=true;
  Positions::saved.calibrating=true; assert(batchAction("A1")==409); Positions::saved.calibrating=false;
  CutSettings::preferences.failWrite=true;
  assert(batchAction("A1")==503 && WebControl::idle());
  CutSettings::preferences.failWrite=false;
  // Sloped mesh: every cut must begin at the same height above the local bed.
  auto &s=Positions::saved;
  for (int r=0;r<3;++r) for (int c=0;c<3;++c) {
    s.mesh[r*3+c][0]=(BedMesh::columns[c]-1)*254;
    s.mesh[r*3+c][1]=-BedMesh::rows[r]*254;
    s.mesh[r*3+c][2]=r*40+c*20;
  }
  s.meshSet=true;
  emitted[3]+=200; initial[3]+=200; // Cut starting height differs from saved A1.
  assert(batchAction(" a1,\nB2, b2 ")==200 && batchRunning && !WebControl::idle());
  assert(action("home")==409 && batchAction("Z34")==409 && cutAction()==409);
  char jog[]="JOG X 10"; command(jog); assert(activeMotor<0); // Between legs still busy.
  const int wifiState=WiFi.state; WiFi.state=0;
  clockUs+=Config::webIdleMs*1000+1000; // No poll keeps this job alive.
  Serial.txFree=0; const int blocked=Serial.blockedWrites;
  size_t seen=0; bool cutting=false, returned=false; int64_t lastSpindle=emitted[2];
  for (int i=0;batchRunning && i<40000;++i) {
    loop();
    if (cutPhase && !cutting) {
      const long col=seen?2:1,row=seen?1:0;
      int64_t x,y; WebControl::holeOffset(col,row,x,y);
      assert(emitted[0]==s.home[0]+x && emitted[1]==s.home[1]+y);
      assert(emitted[3]==initial[3]+WebControl::bedHeight(x,y));
      assert(WebControl::batchIndex==seen); ++seen;
    }
    if (!cutPhase && !cutting) assert(emitted[2]==lastSpindle); // Spindle off in transit.
    cutting=cutPhase!=0; lastSpindle=emitted[2];
    if (WebControl::batchReturning) {
      returned=true;
      assert(batchRunning && !WebControl::idle() && WebControl::batchIndex==3);
      assert(WebControl::target[0]==s.home[0] && WebControl::target[1]==s.home[1] && WebControl::target[3]==s.home[3]);
      assert(WebControl::clearance>=s.home[3]+220); // Above the highest mesh point.
    }
  }
  assert(!batchRunning && WebControl::idle() && seen==3 && WebControl::batchIndex==3);
  assert(returned && WebControl::batchReturned);
  assert(emitted[0]==s.home[0] && emitted[1]==s.home[1] && emitted[3]==s.home[3]);
  assert(Positions::known && Serial.blockedWrites==blocked);
  WiFi.state=wifiState; Serial.txFree=-1;
  // The return also lifts with no mesh, and STOP/storage failures cancel it.
  s.meshSet=false;
  for (bool fail : {false,true}) {
    action("stop"); action("home"); action("arm"); assert(batchAction("B2")==200);
    for (int i=0;!WebControl::batchReturning && i<20000;++i) loop();
    assert(WebControl::batchReturning && batchRunning && !WebControl::batchReturned);
    assert(WebControl::clearance>=emitted[3]+100);
    if (fail) { Positions::preferences.failWrite=true; loop(); Positions::preferences.failWrite=false; }
    else { loop(); delay(50); action("stop"); }
    assert(!batchRunning && !WebControl::batchReturned);
    int64_t stopped[4]; Positions::snapshot(stopped);
    for (int i=0;i<1000;++i) loop();
    for (int m=0;m<4;++m) assert(emitted[m]==stopped[m]);
  }
  // STOP cancels during travel, cutting, and the gap after a completed cut.
  for (int when=0;when<3;++when) {
    action("stop"); action("home"); action("arm"); assert(batchAction("B2,A1")==200);
    if (!when) { loop(); delay(50); assert(activeMotor>=0); }
    if (when) {
      while (!cutPhase) loop();
      if (when==2) { delay(10000); finishMotion(); assert(activeMotor<0 && !presetRunning); }
    }
    assert(action("stop")==200 && !batchRunning);
    int64_t stopped[4]; Positions::snapshot(stopped);
    for (int i=0;i<1000;++i) loop();
    for (int m=0;m<4;++m) assert(emitted[m]==stopped[m]);
    assert(WebControl::idle());
  }
  // A travel checkpoint failure aborts before the first cut.
  action("home"); action("arm"); const int64_t a=emitted[2];
  assert(batchAction("B2,A1")==200); loop();
  Positions::preferences.failWrite=true;
  for (int i=0;batchRunning && i<5000;++i) loop();
  assert(!batchRunning && !armed && !Positions::known && emitted[2]==a);
  Positions::preferences.failWrite=false;
}
void testCutSettings() {
  action("stop");
  auto &prefs=CutSettings::preferences;
  prefs.blob.clear(); CutSettings::begin();
  assert(CutSettings::saved.depth==100 && CutSettings::saved.rpm==60 && CutSettings::saved.feed==200);
  assert(!CutSettings::stored);
  const uint32_t legacy[]={1,250,180,350};
  prefs.putBytes("settings",legacy,sizeof(legacy)); CutSettings::begin();
  assert(CutSettings::saved.version==2 && CutSettings::saved.depth==250 && CutSettings::saved.rpm==180 &&
    CutSettings::saved.feed==350 && CutSettings::saved.accel==75 && !CutSettings::stored);
  // Explicit save requires no motors or reference and never starts motion.
  assert(cutAction("2.5","180","3.5","cut-settings")==200);
  assert(!armed && WebControl::idle());
  const int writes=prefs.writes;
  assert(cutAction("2.5","180","3.5","cut-settings")==200 && prefs.writes==writes);
  CutSettings::saved={}; CutSettings::begin(); // Reload as on boot.
  assert(CutSettings::saved.depth==250 && CutSettings::saved.rpm==180 && CutSettings::saved.feed==350);
  WebControl::state();
  assert(WebControl::server.body.find("\"cutSettings\":{\"depth\":2.5,\"rpm\":180,\"feed\":3.5,\"accel\":75}")!=std::string::npos);
  assert(cutAction("2.5","180","3.5","cut-settings","150")==200);
  CutSettings::begin(); assert(CutSettings::saved.accel==150);
  const int accelWrites=prefs.writes;
  assert(cutAction("2.5","180","3.5","cut-settings","150")==200 && prefs.writes==accelWrites);
  const auto blob=prefs.blob;
  assert(cutAction("2.5","241","3.5","cut-settings")==400 && prefs.blob==blob);
  prefs.failWrite=true;
  assert(cutAction("3","180","3.5","cut-settings")==503 && prefs.blob==blob);
  action("home"); action("arm");
  assert(cutAction("3","180","3.5")==503 && WebControl::idle());
  assert(CutSettings::saved.depth==250);
  prefs.failWrite=false;
  assert(cutAction("3","180","3.5")==200); // Cut also saves settings.
  assert(CutSettings::saved.depth==300);
  assert(cutAction("4","180","3.5","cut-settings")==409); // No writes during motion.
  action("stop");
  // Corrupt, obsolete, or truncated records fall back to defaults.
  for (auto bad : {CutSettings::Record{3,100,60,200}, {2,1001,60,200}, {2,100,241,200}, {2,100,60,2001}, {2,100,60,200,0}, {2,100,60,200,751}}) {
    prefs.putBytes("settings",&bad,sizeof(bad)); CutSettings::begin();
    assert(!CutSettings::stored && CutSettings::saved.depth==100 && CutSettings::saved.rpm==60 && CutSettings::saved.feed==200);
  }
  prefs.blob.resize(3); CutSettings::begin(); assert(!CutSettings::stored);
  prefs.blob.clear(); CutSettings::begin();
}
void testCut() {
  action("stop"); assert(cutAction()==409);
  action("home"); action("arm");
  Positions::known=false; assert(cutAction()==409); Positions::known=true;
  Positions::saved.calibrating=true; assert(cutAction()==409); Positions::saved.calibrating=false;
  Positions::preferences.failWrite=true;
  assert(cutAction()==503 && WebControl::idle() && !cutPhase);
  Positions::preferences.failWrite=false;
  for (const char *bad : {"", "0", "-1", "10.1", "0.15", "nan", "inf", "1junk"})
    assert(cutAction(bad)==400 && WebControl::idle());
  for (const char *bad : {"", "0", "-1", "241", "1.5", "nan", "60rpm"})
    assert(cutAction("1",bad)==400 && WebControl::idle());
  for (const char *bad : {"", "0", "-1", "20.1", "0.15", "nan", "inf", "2junk"})
    assert(cutAction("1","60",bad)==400 && WebControl::idle());
  for (const char *bad : {"", "0", "14", "751", "75.5", "nan", "100junk"})
    assert(cutAction("1","60","2","cut",bad)==400 && WebControl::idle());
  assert(action("cut")==400); // Stale pages must supply explicit settings.
  WebControl::server.args={{"op","cut"},{"client","another-browser"}};
  WebControl::action(); assert(WebControl::server.code==409);
  // Exercise both parameter boundaries and a fractional depth. No browser
  // heartbeats; Wi-Fi is absent and the USB transmit buffer stays full.
  const int wifiState=WiFi.state; WiFi.state=0; Serial.txFree=0;
  const int blocked=Serial.blockedWrites;
  for (auto setting : {std::pair<const char *,const char *>{"0.1","1"}, {"2.5","60"}, {"0.1","240"}, {"10","240"}}) {
    action("stop"); action("home"); action("arm");
    const long depth=std::lround(std::stod(setting.first)*100);
    const long rate=(std::stol(setting.second)*800+30)/60;
    int64_t before[4]; Positions::snapshot(before);
    const size_t zs=riseTimes[D9].size(), as=riseTimes[D5].size();
    assert(cutAction(setting.first,setting.second)==200 && presetRunning && cutPhase==1);
    assert(cutAction()==409 && action("jog","X","10")==409 && action("home")==409);
    long atDepth=-1, atRetract=-1;
    // Advance only the hardware timer, with no loop() at all: stage changes
    // and both axes must continue even if a synchronous HTTP call blocks.
    for (int i=0;!motionComplete && i<3000000;++i) {
      delayMicroseconds(50);
      if (cutPhase==2) {
        assert(emitted[3]==before[3]-depth);
        if (atDepth<0) atDepth=emitted[2]+cutDwell-1600;
      }
      if (cutPhase==3 && atRetract<0) atRetract=emitted[2];
    }
    assert(motionComplete && cutPhase==4 && !Positions::saved.clean);
    assert(atDepth>before[2] && atRetract-atDepth==1600);
    assert(emitted[0]==before[0] && emitted[1]==before[1] && emitted[3]==before[3]);
    assert(riseTimes[D9].size()==zs+2*depth);
    const auto &zt=riseTimes[D9], &at=riseTimes[D5];
    assert(at[as]<=zt[zs] && at.back()>zt.back());
    // There are spindle pulses during both Z legs, with no stop at either
    // dwell transition. Outside acceleration/deceleration gaps stay at cruise.
    bool plunge=false,retract=false;
    for (size_t i=as+1;i<at.size();++i) {
      const auto t=at[i], gap=t-at[i-1];
      assert(gap>=uint32_t(1000000/rate));
      if (t>zt[zs] && t<zt[zs+depth-1]) plunge=true;
      if (t>zt[zs+depth] && t<zt.back()) retract=true;
      if (i-as>cutSpinProfile.rampCount && t<=zt.back())
        assert(gap<=cutSpinProfile.cruise+10);
      if (i>as+1 && at[i-1]>zt.back())
        assert(gap+10>=at[i-1]-at[i-2]); // Decelerate from actual, not requested, speed.
    }
    // The shallowest move at 1 RPM can have no extra spindle pulse during
    // its short Z leg; at normal cutting speeds both overlaps are required.
    if (rate>100) assert(plunge && retract);
    loop();
    assert(WebControl::idle() && !cutPhase && Positions::known && Positions::saved.clean);
    assert(Serial.blockedWrites==blocked);
  }
  WiFi.state=wifiState; Serial.txFree=-1;
  // Acceleration settings affect the actual spindle pulse ramp, including
  // the slowest supported ramp at maximum RPM (the largest workspace).
  for (const char *accel : {"15","150","750"}) {
    action("stop"); action("home"); action("arm");
    const int64_t z=emitted[3]; const size_t first=riseTimes[D5].size();
    assert(cutAction("1","240","2","cut",accel)==200);
    const long a=(std::stol(accel)*800+30)/60;
    assert(cutSpinProfile.rampCount==uint32_t((3200*3200+2*a-1)/(2*a)));
    assert(cutSpinProfile.ramp[0]==uint32_t(std::ceil(std::sqrt(2.0/a)*1000000)));
    delay(60000); loop();
    assert(WebControl::idle() && emitted[3]==z && !cutPhase);
    for (size_t i=1;i<20;++i) {
      const uint32_t gap=riseTimes[D5][first+i]-riseTimes[D5][first+i-1];
      assert(gap>=cutSpinProfile.ramp[i] && gap<=cutSpinProfile.ramp[i]+10);
    }
  }
  // The selected feed controls both Z legs. Check actual pulse intervals,
  // including fractional and boundary feeds, while the timer runs alone.
  for (const char *feed : {"0.1","1","2","2.5","20"}) {
    action("stop"); action("home"); action("arm");
    const int count=std::stod(feed)<1 ? 100:1000;
    const int64_t z=emitted[3]; const size_t first=riseTimes[D9].size();
    assert(cutAction(count==100 ? "1":"10","60",feed)==200);
    delay(40000); loop();
    assert(WebControl::idle() && emitted[3]==z);
    assert(riseTimes[D9].size()==first+2*count);
    assert(cutZProfile.cruise==uint32_t(std::ceil(1000000/(std::stod(feed)*100))));
    for (int leg=0;leg<2;++leg) for (int i=1;i<count;++i) {
      const size_t index=first+leg*count+i;
      const uint32_t gap=riseTimes[D9][index]-riseTimes[D9][index-1];
      assert(gap>=cutZProfile.interval(i) && gap<=cutZProfile.interval(i)+10);
    }
  }
  for (int phase=1;phase<=4;++phase) {
    action("stop"); action("home"); action("arm");
    assert(cutAction()==200);
    for (int i=0;cutPhase!=phase && i<15000;++i) loop();
    assert(cutPhase==phase);
    delay(1);
    assert(action("stop")==200 && !cutPhase && !presetRunning);
    int64_t stopped[4]; Positions::snapshot(stopped);
    delay(20000); loop();
    for (int m=0;m<4;++m) assert(emitted[m]==stopped[m]);
    assert(!armed && !Positions::known);
  }
  // A final checkpoint failure invalidates the reference, never restarts a cut.
  action("home"); action("arm"); assert(cutAction()==200);
  Positions::preferences.failWrite=true;
  delay(20000); loop();
  assert(WebControl::idle() && !cutPhase && !Positions::known);
  assert(cutAction()==409);
  Positions::preferences.failWrite=false;
  action("stop");
  // Cutting and DEMO reuse RAM; each must reinitialize its own planner.
  const bool connected=Serial.connected; Serial.connected=true;
  char armCommand[]="ARM", demoCommand[]="DEMO";
  command(armCommand); command(demoCommand);
  assert(demoRunning && demoCount>0);
  delay(100); action("stop"); action("home"); action("arm");
  assert(cutAction("1","240")==200);
  delay(30000); loop(); assert(WebControl::idle() && !cutPhase);
  action("stop"); Serial.connected=connected;
}
int main() {
  setup(); WiFi.state=WL_CONNECTED; Serial.connected=false;
  // A connected client that sends nothing is dropped after 400 ms, not the
  // stock 5 s that would starve the 3 s lease and stop the motors.
  WebControl::server._currentStatus=HC_WAIT_READ; WebControl::server._statusChange=millis();
  delay(300); WebControl::service();
  assert(WebControl::server._currentStatus==HC_WAIT_READ && !WebControl::server._currentClient.stopped);
  delay(200); WebControl::service();
  assert(WebControl::server._currentStatus==HC_NONE && WebControl::server._currentClient.stopped);
  WebControl::server._currentStatus=HC_WAIT_READ; WebControl::server._statusChange=millis();
  WebControl::server._currentClient={1,false}; delay(600); WebControl::service();
  assert(!WebControl::server._currentClient.stopped); // Data pending: not silent.
  WebControl::server._currentStatus=HC_NONE; WebControl::server._currentClient={};
  assert(action("arm")==403 && !armed);
  WebControl::server.headers["X-XYZ-Control"]="1";
  // Repeated 0.1 mm jogs used to fill unread USB output and then block both
  // the action reply (OK jogging) and the next poll (DONE) for seconds.
  Serial.connected=true;
  Serial.txFree=64;
  assert(action("arm")==200);
  const int64_t start=emitted[0];
  for (int i=0;i<100;++i) {
    const uint32_t began=millis();
    assert(action("jog","X",i%2 ? "-10":"10")==200);
    run();
    assert(action("poll")==200);
    assert(uint32_t(millis()-began)<300);
    assert(Serial.blockedWrites==0);
  }
  assert(emitted[0]==start);
  // Also cover a completely full queue, re-arming, and the one-byte-short
  // boundary where DONE would fit but its CRLF would block.
  for (int space : {0,5}) {
    Serial.txFree=space;
    assert(action("stop")==200);
    assert(action("arm")==200);
    assert(action("jog","X","10")==200); run();
    assert(action("jog","X","-10")==200); run();
    assert(Serial.blockedWrites==0);
  }
  assert(action("stop")==200);
  Serial.txFree=-1;
  Serial.connected=false;
  assert(action("replace")==409);
  assert(action("arm")==200 && armed && webArmed);
  WebControl::server.args={{"op","heartbeat"},{"client","different-browser"}};
  WebControl::action(); assert(WebControl::server.code==409);
  // An open controlling page must survive the former 30-second idle cutoff.
  for (int i=0;i<35;++i) { action("poll"); delay(1000); loop(); }
  assert(armed && webArmed);
  // A transient delay longer than the old lease still recovers.
  delay(1800); action("poll"); loop(); assert(armed);
  WebControl::server.args={{"op","hidden"},{"client","test-browser-0001"}};
  WebControl::action(); assert(armed); // A hidden page no longer stops anything.
  assert(action("jog","A","10")==400);
  assert(action("jog","Z","1001")==400);
  assert(action("jog","X","1junk")==400);
  assert(action("jog","X","100")==200);
  assert(action("home")==409); // No saving while moving.
  run(); assert(emitted[0]==100 && armed); // Works with USB disconnected.
  assert(action("home")==200 && Positions::known);
  assert(action("jog","Z","100")==200); run();
  assert(action("jog","X","100")==200); run();
  assert(action("jog","Y","100")==200); run();
  assert(action("replace")==200);
  const int spindle=rises[D5];
  assert(action("go-home")==200);
  WebControl::service(); assert(lineRunning && activeMotor>=0); // Already at higher Z: cross first.
  run(); assert(emitted[0]==100 && emitted[1]==0 && emitted[3]==0);
  assert(rises[D5]==spindle);
  assert(action("go-replace")==200);
  WebControl::service(); assert(activeMotor==3); // Raise Z before XY.
  run(); assert(emitted[0]==200 && emitted[1]==100 && emitted[3]==100);
  // Go to a hole by name: raise Z by 1 mm, one straight XY line, then back
  // down to the starting height.
  assert(action("goto")==400);
  for (const char *bad : {"A0", "A35", "AA1", " B2", "B 2", "B2 ", "B+2", "2B", "B", "B2x"}) {
    WebControl::server.args={{"op","goto"},{"hole",bad},{"client","test-browser-0001"}};
    WebControl::action(); assert(WebControl::server.code==400);
  }
  assert(WebControl::roundDiv(5,2)==3 && WebControl::roundDiv(-5,2)==-2); // Halves up, like Math.round.
  assert(WebControl::roundDiv(-7,2)==-3 && WebControl::roundDiv(7,3)==2 && WebControl::roundDiv(-7,3)==-2 && WebControl::roundDiv(-8,3)==-3);
  WebControl::server.args={{"op","goto"},{"hole","c2"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200);
  const int64_t zStart=emitted[3];
  WebControl::service(); assert(activeMotor==3 && !lineRunning); // Lift first.
  {
    const size_t x0=riseTimes[D1].size(), y0=riseTimes[D3].size();
    while (activeMotor==3) loop();
    assert(emitted[3]==zStart+100 && riseTimes[D1].size()==x0 && riseTimes[D3].size()==y0); // XY waited for the lift.
    WebControl::service(); assert(activeMotor==1 && lineRunning && !demoRunning); // One straight line; Y is the longer axis.
    while (activeMotor==1) loop();
    assert(emitted[3]==zStart+100 && riseTimes[D1].back() > riseTimes[D3][y0]); // X and Y overlapped, not in turn.
    WebControl::service(); assert(activeMotor==3 && !lineRunning); // Lower only after XY has finished.
    run(); assert(emitted[3]==zStart); // Back to the starting height.
    assert(armed && !lineRunning && WebControl::idle()); // Unlike DEMO, stays armed.
  }
  assert(emitted[0]==Positions::saved.home[0]+254 && emitted[1]==Positions::saved.home[1]-508);
  assert(emitted[3]==Positions::saved.replace[3]);
  // An axis-aligned hole move to row Z cruises at 4,000 pulses/sec.
  WebControl::server.args={{"op","goto"},{"hole","Z2"},{"client","test-browser-0001"}};
  { const size_t y0=riseTimes[D3].size(); const int xPulses=rises[D1];
    WebControl::action(); assert(WebControl::server.code==200); run();
    assert(rises[D1]==xPulses && emitted[1]==Positions::saved.home[1]-6350);
    const uint32_t gap=riseTimes[D3][y0+2001]-riseTimes[D3][y0+2000];
    assert(gap>=249 && gap<=251); }
  { const int64_t z=emitted[3]; WebControl::action(); assert(WebControl::server.code==200 && WebControl::idle()); // Already there: no lift either.
    run(); assert(emitted[3]==z); }
  WebControl::server.args={{"op","goto"},{"hole","B1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  // Calibrate the grid: boards are not exactly on a 2.54 mm pitch. Saving
  // Z34 far from its nominal place is refused as a probable wrong hole.
  const int64_t *home=Positions::saved.home;
  assert(action("span")==409 && !Positions::saved.spanSet);
  WebControl::state(); assert(WebControl::server.body.find("\"spanSet\":false")!=std::string::npos);
  WebControl::server.args={{"op","goto"},{"hole","Z34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+8382 && emitted[1]==home[1]-6350); // Nominal grid until Z34 is set.
  assert(action("jog","X","80")==200); run(); assert(action("jog","Y","-60")==200); run();
  assert(action("span")==200 && Positions::saved.spanSet);
  assert(Positions::saved.span[0]==8462 && Positions::saved.span[1]==-6410 && Positions::saved.clean);
  WebControl::state(); assert(WebControl::server.body.find("\"spanSet\":true")!=std::string::npos);
  assert(WebControl::server.body.find("\"span\":[8462,-6410]")!=std::string::npos);
  // Holes interpolate per axis between A1 and Z34, rounded to whole pulses.
  WebControl::server.args={{"op","goto"},{"hole","A34"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+8462 && emitted[1]==home[1]);
  WebControl::server.args={{"op","goto"},{"hole","M12"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+2821 && emitted[1]==home[1]-3077); // 8462*11/33, -6410*12/25.
  // Arrow steps in whole holes use the local calibrated pitch, so an on-grid
  // start lands on the grid and an off-grid start keeps its offset.
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+3077); // Column 13: 8462*12/33.
  WebControl::server.args={{"op","jog"},{"axis","Y"},{"holes","-1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[1]==home[1]-3333); // Row N: -6410*13/25.
  assert(action("jog","X","10")==200); run();
  WebControl::server.args={{"op","jog"},{"axis","X"},{"holes","-1"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[0]==home[0]+2821+10);
  WebControl::server.args={{"op","jog"},{"axis","Y"},{"holes","3"},{"client","test-browser-0001"}};
  WebControl::action(); assert(WebControl::server.code==200); run();
  assert(emitted[1]==home[1]-2564); // Row K: -6410*10/25.
  for (auto bad : {std::pair<const char*,const char*>{"X","4"}, {"Z","1"}, {"X","0"}, {"Y","-4"}, {"X","1.5"}}) {
    WebControl::server.args={{"op","jog"},{"axis",bad.first},{"holes",bad.second},{"client","test-browser-0001"}};
    WebControl::action(); assert(WebControl::server.code==400);
  }
  assert(WebControl::nearestIndex(0,8462)==34 && WebControl::nearestIndex(0,128)==1 && WebControl::nearestIndex(0,129)==2);
  assert(WebControl::nearestIndex(1,-6410)==25 && WebControl::nearestIndex(1,-128)==0 && WebControl::nearestIndex(1,-129)==1);
  assert(WebControl::nearestIndex(0,-300)==0 && WebControl::nearestIndex(1,300)==-1); // Off-board extrapolation.
  assert(action("go-replace")==200); run(); // Back where the reboot check expects.
  assert(emitted[0]==Positions::saved.replace[0] && emitted[1]==Positions::saved.replace[1]);
  action("stop");
  Positions::begin(); // Clean reboot restores counts but requires confirmation.
  assert(!Positions::known && Positions::saved.homeSet && Positions::saved.replaceSet && Positions::saved.spanSet);
  assert(Positions::saved.clean && emitted[0]==200);
  action("arm"); assert(action("go-home")==409);
  assert(action("confirm")==200 && Positions::known);
  // Power loss after motion starts leaves no recoverable checkpoint.
  assert(action("jog","X","500")==200);
  assert(!Positions::saved.clean);
  delay(100); timerStop(stepTimer); activeMotor=-1; remaining=0;
  disableMotors(); Positions::begin();
  assert(!Positions::saved.clean && !Positions::known);
  assert(action("confirm")==409);
  assert(action("reference")==200 && emitted[0]==100 && emitted[3]==0);
  assert(Positions::saved.replaceSet);
  // Storage failure rejects motion before the first pulse and preserves presets.
  Positions::preferences.failWrite=true;
  assert(action("home")==409);
  action("arm"); const int before=rises[D1];
  assert(action("jog","X","100")==503);
  delay(100); assert(rises[D1]==before);
  Positions::preferences.failWrite=false;
  // No dead-man's handle: a move completes with no polls at all and through
  // network loss. Idle motors are released after a minute without the page.
  WebControl::runCommand("JOG Y 2000 200");
  assert(activeMotor==1);
  const int64_t yBefore=emitted[1];
  WiFi.state=0;
  delay(Config::webIdleMs+100);
  WebControl::service(); assert(armed && activeMotor==1); // Still moving: not released.
  finishMotion(); assert(activeMotor==-1 && armed && emitted[1]==yBefore+2000 && Positions::known);
  WebControl::service(); // Idle and unheard-from for a minute: release.
  assert(!armed && std::string(disableReason)=="Control page away for 60 s");
  WiFi.state=WL_CONNECTED;
  action("arm");
  for (const char *axis : {"X", "Y", "Z"}) {
    const int m=axisMotor[axisIndex(axis)];
    const int64_t start=emitted[m];
    assert(action("jog",axis,"1000")==200);
    assert(stepIntervals[499]>=1000 && stepIntervals[499]<=1001); // 1,000 pulses/sec cruise.
    run(); assert(emitted[m]==start+1000);
    assert(action("jog",axis,"-1000")==200);
    run(); assert(emitted[m]==start);
  }
  // Stopping mid-move leaves the position unknown.
  assert(action("jog","X","1000")==200); delay(100); action("stop");
  assert(!armed && !Positions::known);
  // Establishing a different, unknown home invalidates the old replacement,
  // but the Z34 offset describes the board and scale, so it is kept.
  assert(action("home")==200 && !Positions::saved.replaceSet && Positions::saved.spanSet);
  Positions::begin(); assert(Positions::saved.homeSet && !Positions::saved.replaceSet && Positions::saved.spanSet);
  // A version 1 record (no Z34) loads with the nominal grid; the next write upgrades it.
  {
    auto &blob=Positions::preferences.blob; const auto keep=Positions::saved;
    assert(blob.size()==sizeof(Positions::Record));
    blob.resize(Positions::legacySize); const uint32_t v1=1; memcpy(blob.data(), &v1, sizeof(v1));
    Positions::begin();
    assert(Positions::saved.version==3 && Positions::saved.homeSet && !Positions::saved.spanSet && blob.size()==Positions::legacySize);
    int64_t x,y; WebControl::holeOffset(34,25,x,y); assert(x==8382 && y==-6350);
    assert(Positions::write(Positions::saved) && blob.size()==sizeof(Positions::Record));
    const uint32_t bad=99; memcpy(blob.data(), &bad, sizeof(bad));
    Positions::begin(); assert(!Positions::saved.homeSet); // Unknown versions are ignored.
    Positions::ready=true; assert(Positions::write(keep)); Positions::begin();
    assert(Positions::saved.homeSet && Positions::saved.spanSet);
  }
  WebControl::state(); assert(WebControl::server.body.find("\"known\":false")!=std::string::npos);
  // Preset distances exceed both manual jog caps and the 6,000-entry jog
  // buffer. Verify every cruise gap across former chunk boundaries, XYZ in
  // both directions, with only one start/stop per leg. X and Y share one
  // diagonal line at 4,000 pulses/sec along the path: 4000/sqrt(2) per axis.
  assert(action("confirm")==200);
  auto preset = Positions::saved;
  constexpr int travel=7001;
  for (int m : {0,1,3}) preset.replace[m]=preset.home[m]+travel;
  preset.replaceSet=true;
  assert(Positions::write(preset));
  action("arm");
  for (const char *op : {"go-replace","go-home"}) {
    size_t starts[4];
    for (int m : {0,1,3}) starts[m]=riseTimes[Config::stepPins[m]].size();
    const int spindleBefore=rises[D5];
    assert(action(op)==200);
    run();
    assert(rises[D5]==spindleBefore);
    for (int m : {0,1,3}) {
      const auto &times=riseTimes[Config::stepPins[m]];
      assert(times.size()-starts[m]==travel);
      const int margin = m==3 ? 51 : 600; // Diagonal ramp: 800 path pulses.
      for (int i=margin;i<travel-margin;++i) {
        const uint32_t gap=times[starts[m]+i]-times[starts[m]+i-1];
        if (m==3) assert(gap>=1000 && gap<=1001); else assert(gap>=353 && gap<=355);
      }
      if (m==0) assert(riseTimes[D1][starts[0]]==riseTimes[D3][starts[1]]); // Same tick.
      const int64_t expected=std::string(op)=="go-home" ? preset.home[m] : preset.replace[m];
      assert(emitted[m]==expected);
    }
  }
  assert(action("go-replace")==200); WebControl::service(); delay(100);
  assert(presetProfileActive && remaining>0);
  assert(action("stop")==200);
  const int stoppedZ=rises[D9]; delay(1000);
  assert(rises[D9]==stoppedZ && !presetRunning && !Positions::known);
  testMesh();
  testCutSettings();
  testCut();
  testBatch();
  // Compare compressed and full profiles, including short triangular moves
  // and odd lengths. Mirrored floating-point rounding differs by at most 1 us.
  for (int count : {1,2,3,49,50,51,99,100,101,1000,6000}) {
    assert(presetProfile.build(count,1000,10000));
    buildProfile(stepIntervals,count,1000,10000);
    for (int i=0;i<count;++i)
      assert(std::abs(int64_t(presetProfile.interval(i))-stepIntervals[i])<=1);
  }
  std::cout << "Web control and position persistence tests passed\n";
}
