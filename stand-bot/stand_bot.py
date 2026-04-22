from stripboard import *

designing = True

def buck3a(sb,x,y):
    y = sb.row(y)
    sb.vtext(x + 6.8,y,'BUCK')
    sb.sip(x,y,4,'',pins=['EN','IN+','GND','VO+'],labelScale=0.55)
    sb.box(x - 0.5,y - 0.5,7.9,4)


def mpu6050(sb,x,y):
    y = sb.row(y)
    sb.sip(x,y,8,'',
        pins=['VCC','GND','SCL','SDA','XDA','XCL','ADO','INT'],
        labelScale=0.55)
    sb.vtext(x + 3,y,'MPU-6050')


def drawBoard(sb):
    # 3A Buck (top left)
    buck3a(sb,11,'G')

    # MPU-6050 IMU (mid left)
    mpu6050(sb,1,'F')

    # RP2040 (XIAO) (right)
    sb.dip(7,'L',name='RP2040',w=6,h=7,labelScale=0.55,upside_down=True,
        pins=['D0','D1','D2','D3','SDA','SCL',
              'TX','RX','D8','D9','D10','3V3','GND','5V']
    )

    sb.vtext(7,'A','POWER')

    sb.sip(9,'A',2,'-')
    sb.sip(10,'A',2,'')
    sb.sip(11,'A',2,'')

    sb.sip(9,'D',2,'+')
    sb.sip(10,'D',2,'')
    sb.sip(11,'D',2,'')

    sb.sip(18,'N',3,'SERVO')

    sb.cut(8,'A','G')
    sb.cut(14,'L','O')
    sb.cut(11,'O','R')
    sb.cut(11,'L')
    sb.cut(12,'J')
    sb.cut(10,'G','H')
    
    # I2C
    sb.cut(2,'M','N')
    sb.cut(5,'H','L')
    sb.jumper(3,'H',3,'M')
    sb.jumper(4,'I',4,'N')

    sb.jumper(10,'D',10,'E')
    sb.jumper(10,'A',10,'B')
    sb.jumper(14,'E',14,'H')
    sb.jumper(15,'O',15,'H')

    # 3V3
    sb.jumper(9,'I',9,'Q')
    sb.jumper(10,'J',10,'P')
    sb.jumper(6,'I',6,'G')
    sb.jumper(7,'J',7,'F')

    sb.jumper(17,'B',17,'I')
    sb.jumper(16,'I',16,'N')

    sb.trace(9,'D')
    sb.trace(9,'B')
    sb.trace(18,'P')

    sb.trace(13,'M')
    sb.trace(13,'N')

    sb.trace(11,'J')


def drawBuild(sb,y,drawBoardLambda,boardWidth=18,boardHeight="R"):
    w = 40.5
    yy = 38
    sb.beginBoard(boardWidth,boardHeight,showStrips=False,at=(-w,y - yy),
        showTraces=False,showCrosses=False,title="FRONT",rotate=True)
    drawBoardLambda(sb)
    sb.endBoard()

    sb.beginBoard(boardWidth,boardHeight,flipX=True,showStrips=True,
        at=(0,y - yy),showTraces=False,showCrosses=True,
        showComponents=False,showJumpers=False,title="BACK",rotate=True)
    drawBoardLambda(sb)
    sb.endBoard()

    sb.beginBoard(boardWidth,boardHeight,showStrips=True,at=(w,y - yy),
        showTraces=True,title="DESIGN",rotate=True)
    drawBoardLambda(sb)
    sb.endBoard()


if designing:
    sb = StripBoard(pageWidth=40.5,pageHeight=34)
    sb.beginBoard(18,"R",showStrips=True,at=(0,0),
        showTraces=True,title="DESIGN",rotate=True)
    drawBoard(sb)
    sb.endBoard()
    sb.gen('stand_bot.pdf')
else:
    w = 40.5 * 3
    h = w * 1.294
    sb = StripBoard(pageWidth=w,pageHeight=h)
    drawBuild(sb,0,drawBoard,boardWidth=18,boardHeight="R")
    sb.gen('stand_bot.pdf')

    sb = StripBoard(pageWidth=32,pageHeight=28,blackAndWhite=True)
    sb.beginBoard(18,"R",showStrips=False,at=(0,0),
        showTraces=False,showCrosses=False,showCoordinates=False,rotate=True)
    drawBoard(sb)
    sb.endBoard()
    sb.gen('stand_bot_label.pdf')
