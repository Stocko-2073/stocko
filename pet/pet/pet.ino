#include <U8g2lib.h>
#include "stocko_logo.h"

#ifdef U8X8_HAVE_HW_SPI
#include <SPI.h>
#endif
#ifdef U8X8_HAVE_HW_I2C
#include <Wire.h>
#endif

U8G2_SSD1306_64X48_ER_F_HW_I2C u8g2(U8G2_R2, /* reset=*/ U8X8_PIN_NONE);   // EastRising 0.66" OLED breakout board, Uno: A4=SDA, A5=SCL, 5V powered

int sign(int x) {
    return (x > 0) - (x < 0);
}

void setup() {
  Serial.begin(9600);
  u8g2.begin();
  u8g2.setFont(u8g2_font_jinxedwizards_tr);
  // u8g2.setFont(u8g2_font_glasstown_nbp_tr);	// choose a suitable font
  // u8g2.setFont(u8g2_font_glasstown_nbp_tr);	// choose a suitable font
  // u8g2.drawStr(0,12,"Hello my");	// write something to the internal memory
  // u8g2.drawStr(0,28,"moots!");	// write something to the internal memory
}

void drawEyes(int x,int y,int blink) {
  static float radius=31.0f;
  static float eyeTheta0 = asin(18.0f / radius);
  int r=blink<17 ? 4 : (24-blink)/2;
  float rot  = x * 0.125f;
  float angL = rot - eyeTheta0;
  float angR = rot + eyeTheta0;
  float cL=cos(angL), sL=sin(angL);
  float cR=cos(angR), sR=sin(angR);

  int wL = (int)(16*cL + 0.5f);
  int wR = (int)(16*cR + 0.5f);
  int xL = 32 + (int)(radius*sL) - wL/2;
  int xR = 32 + (int)(radius*sR) - wR/2;
  int rL = wL/2 < r ? wL/2 : r;
  int rR = wR/2 < r ? wR/2 : r;
  int h  = 24 - blink;

  u8g2.clearBuffer();
  u8g2.setDrawColor(1);
  if (cL > 0 && wL >= 2 && h > 2*rL) {
    u8g2.drawRBox(xL, 4+y+blink, wL, h, rL);
    u8g2.drawHLine(xL-2, 4+rL+y+blink, 2);
  }
  if (cR > 0 && wR >= 2 && h > 2*rR) {
    u8g2.drawRBox(xR, 4+y+blink, wR, h, rR);
    u8g2.drawHLine(xR+wR, 4+rR+y+blink, 2);
  }
  u8g2.sendBuffer();
} 

void loop() {
  static int x=0,y=0,tx=0,ty=0;
  static int blinkStep=0;
  static unsigned long nextActionMs=0;

  if (tx!=x) x+=sign(tx-x);
  if (ty!=y) y+=sign(ty-y);
  if (tx==x && ty==y && random(50)==0) {
    tx=random(9)-4;
    ty=random(9)-4;
  }

  int i = (blinkStep<12) ? blinkStep*2 : 23-(blinkStep-12)*2;
  drawEyes(x,y,i);

  if ((long)(millis()-nextActionMs)<0) return;
  blinkStep++;

  if (blinkStep>=24) {
    blinkStep=0;
    if (random(10)>2) nextActionMs = millis()+1000UL*(random(4)+1);
  }
}




