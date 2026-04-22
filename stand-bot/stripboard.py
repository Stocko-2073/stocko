from fpdf import FPDF
import math
import subprocess

class AlphaPDF(FPDF):

    def __init__(self, *args, **kwargs):
        FPDF.__init__(self, *args, **kwargs)
        self.pdf_version = '1.4'
        self.set_compression(0)
        self.extgstates = {}

    def set_alpha(self, alpha, bm='Normal'):
        gs = self.AddExtGState({'ca': alpha, 'CA': alpha, 'BM': '/' + bm})
        self.SetExtGState(gs)

    def AddExtGState(self, parms):
        n = len(self.extgstates) + 1
        self.extgstates[n] = {}
        self.extgstates[n]['parms'] = parms
        return n

    def SetExtGState(self, gs):
        self._out('/GS%d gs' % gs)

    def _enddoc(self):
        if len(self.extgstates) > 0 and self.pdf_version < '1.4':
            self.pdf_version = '1.4'
        FPDF._enddoc(self)

    def _putextgstates(self):
        for i in range(1, len(self.extgstates) + 1):
            self._newobj()
            self.extgstates[i]['n'] = self.n
            self._out('<</Type /ExtGState')
            parms = self.extgstates[i]['parms']
            self._out('/ca %.3F' % parms['ca'])
            self._out('/CA %.3F' % parms['CA'])
            self._out('/BM ' + parms['BM'])
            self._out('>>')
            self._out('endobj')

    def _putresourcedict(self):
        FPDF._putresourcedict(self)
        self._out('/ExtGState <<')
        for k, extgstate in self.extgstates.items():
            self._out(f"/GS{k} {extgstate['n']} 0 R")
        self._out('>>')

    def _putresources(self):
        self._putextgstates()
        FPDF._putresources(self)


class StripBoard:

    def __init__(
        self,
        offset_x=2.0,
        offset_y=2.0,
        scale=1.0,
        showTraces=True,
        showNumbers=False,
        showCrosses=True,
        showJumpers=True,
        showComponents=True,
        pageWidth=110,
        pageHeight=85,
        blackAndWhite=False
    ):
        self.vectorChars = {
            ' ': [],
            '!': [[2, 0, 2, 2], [2, 3.8, 2, 4]],
            '\"': [[1, 0, 1, 1], [3, 0, 3, 1]],
            '#': [[1, 0, 1, 4], [3, 0, 3, 4], [0, 1, 4, 1], [0, 3, 4, 3]],
            '$': [[4, 0.5, 1, 0.5, 0, 2, 4, 2, 3, 3.5, 0, 3.5], [2, 0, 2, 4]],
            '%': [[1, 0, 0, 1, 1, 2, 2, 1, 1, 0], [3, 2, 2, 3, 3, 4, 4, 3, 3, 2], [4, 0, 0, 4]],
            '&': [[4, 4, 1, 2, 0.5, 0.5, 2, 0, 3, 1, 0, 3, 1, 4, 2, 4, 4, 3]],
            '\'': [[2, 0, 2, 1]],
            '(': [[2, 0, 1, 1, 1, 3, 2, 4]],
            ')': [[2, 0, 3, 1, 3, 3, 2, 4]],
            '*': [[0.5, 0.5, 3.5, 3.5], [0.5, 3.5, 3.5, 0.5], [2, 0, 2, 4], [0, 2, 4, 2]],
            '+': [[2, 0.5, 2, 3.5], [0.5, 2, 3.5, 2]],
            ',': [[2, 3, 1, 4]],
            '-': [[0.5, 2, 3.5, 2]],
            '.': [[2, 3, 2, 3.3, 2.3, 3.3,  2.3, 3, 2, 3]],
            '/': [[3, 0, 1, 4]],
            '0': [[0, 1, 1, 0, 3, 0, 4, 1, 4, 3, 3, 4, 1, 4, 0, 3, 0, 1], [2, 2, 2, 2.2]],
            '1': [[0, 1, 2, 0, 2, 4], [0, 4, 4, 4]],
            '2': [[0, 1, 1, 0, 3, 0, 4, 1, 0, 4, 4, 4]],
            '3': [[0, 1, 1, 0, 3, 0, 4, 1, 2, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            '4': [[1, 0, 0, 2, 4, 2], [3, 0, 3, 4]],
            '5': [[4, 0, 0, 0, 0, 1.7, 3.5, 1.7, 4, 3, 3.5, 4, 0.5, 4, 0, 3.5]],
            '6': [[3.5, 0, 1, 0, 0, 1, 0, 3, 1, 4, 3, 4, 4, 3, 3, 2, 1, 2, 0, 3]],
            '7': [[0, 0, 4, 0, 4, 1, 1, 4]],
            '8': [[1, 0, 3, 0, 4, 1, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3, 1, 2, 0, 1, 1, 0], [1, 2, 3, 2]],
            '9': [[4, 4, 4, 2, 4, 1, 3, 0, 1, 0, 0, 1, 1, 2, 4, 2]],
            ':': [[2, 1, 2, 1.2], [2, 3, 2, 3.2]],
            ';': [[2, 1, 2, 1.2], [2, 3, 1, 4]],
            '<': [[3, 1, 1, 2, 3, 3]],
            '=': [[1, 1, 3, 1], [1, 3, 3, 3]],
            '>': [[1, 1, 3, 2, 1, 3]],
            '?': [[0, 1, 1, 0, 3, 0, 4, 1, 2, 2], [2, 3.8, 2, 4]],
            '@': [[3, 3, 3, 2, 2, 1, 1, 2, 2, 3, 3, 3, 4, 2, 4, 1, 3, 0, 1, 0, 0, 1, 0, 3, 1, 4, 4, 4]],
            'A': [[0, 4, 0, 2, 2, 0, 4, 2, 4, 4], [0, 3, 4, 3]],
            'B': [[0, 0, 0, 4, 3, 4, 4, 3, 3, 2, 4, 1, 3, 0, 0, 0], [0, 2, 3, 2]],
            'C': [[4, 1, 3, 0, 1, 0, 0, 1, 0, 3, 1, 4, 3, 4, 4, 3]],
            'D': [[0, 0, 0, 4, 3, 4, 4, 3, 4, 1, 3, 0, 0, 0]],
            'E': [[4, 0, 0, 0, 0, 4, 4, 4], [0, 2, 3, 2]],
            'F': [[4, 0, 0, 0, 0, 4], [0, 2, 3, 2]],
            'G': [[4, 0, 1, 0, 0, 1, 0, 3, 1, 4, 3, 4, 4, 3], [4, 4, 4, 2, 2, 2]],
            'H': [[0, 0, 0, 4], [4, 0, 4, 4], [0, 2, 4, 2]],
            'I': [[0, 0, 4, 0], [0, 4, 4, 4], [2, 0, 2, 4]],
            'J': [[4, 0, 4, 3, 3, 4, 1, 4, 0, 3]],
            'K': [[0, 0, 0, 4], [4, 0, 0, 2, 4, 4]],
            'L': [[0, 0, 0, 4, 4, 4]],
            'M': [[0, 4, 0, 0, 2, 2, 4, 0, 4, 4]],
            'N': [[0, 4, 0, 0, 4, 4, 4, 0]],
            'O': [[1, 0, 3, 0, 4, 1, 4, 3, 3, 4, 1, 4, 0, 3, 0, 1, 1, 0]],
            'P': [[0, 4, 0, 0, 3, 0, 4, 1, 3, 2, 0, 2]],
            'Q': [[1, 0, 3, 0, 4, 1, 4, 2.5, 2.5, 4, 1, 4, 0, 3, 0, 1, 1, 0], [4, 4, 2, 2]],
            'R': [[0, 4, 0, 0, 3, 0, 4, 1, 3, 2, 0, 2], [2, 2, 4, 4]],
            'S': [[4, 0.5, 3, 0, 1, 0, 0, 1, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3.5]],
            'T': [[0, 0, 4, 0], [2, 0, 2, 4]],
            'U': [[0, 0, 0, 3, 1, 4, 3, 4, 4, 3, 4, 0]],
            'V': [[0, 0, 2, 4, 4, 0]],
            'W': [[0, 0, 0, 4, 2, 2, 4, 4, 4, 0]],
            'X': [[0, 0, 4, 4], [0, 4, 4, 0]],
            'Y': [[0, 0, 2, 2, 4, 0], [2, 2, 2, 4]],
            'Z': [[0, 0, 4, 0, 0, 4, 4, 4]],
            '[': [[3, 0, 1, 0, 1, 4, 3, 4]],
            '\\': [[1, 0, 3, 4]],
            ']': [[1, 0, 3, 0, 3, 4, 1, 4]],
            '^': [[0, 2, 2, 0, 4, 2]],
            '_': [[0, 4, 4, 4]],
            '`': [[1, 0, 2, 1]],
            'a': [[4, 2, 4, 4], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'b': [[0, 0, 0, 4], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'c': [[4, 2, 1, 2, 0, 3, 1, 4, 4, 4]],
            'd': [[4, 0, 4, 4], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'e': [[0, 3, 4, 3, 3, 2, 1, 2, 0, 3, 1, 4, 3, 4]],
            'f': [[4, 1, 3, 0, 2, 1, 2, 4], [1, 2, 3, 2]],
            'g': [[4, 2, 4, 4, 3, 5, 1, 5, 0, 4], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'h': [[0, 0, 0, 4], [0, 3, 1, 2, 3, 2, 4, 3, 4, 4]],
            'i': [[1, 2, 2, 2, 2, 4], [2, 0, 2, 1]],
            'j': [[3, 2, 3, 4, 2, 5, 1, 5, 0, 4], [3, 0, 3, 1]],
            'k': [[0, 0, 0, 4], [4, 2, 0, 3, 4, 4]],
            'l': [[1, 0, 2, 0, 2, 4], [1, 4, 3, 4]],
            'm': [[0, 2, 0, 4], [0, 3, 1, 2, 2, 3, 3, 2, 4, 3, 4, 4], [2, 3, 2, 4]],
            'n': [[0, 2, 0, 4], [0, 3, 1, 2, 3, 2, 4, 3, 4, 4]],
            'o': [[0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'p': [[0, 2, 0, 5], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'q': [[4, 2, 4, 5], [0, 3, 1, 2, 3, 2, 4, 3, 3, 4, 1, 4, 0, 3]],
            'r': [[0, 2, 0, 4], [0, 3, 1, 2, 3, 2, 4, 3]],
            's': [[4, 2, 1, 2, 0, 3, 4, 3, 3, 4, 0, 4]],
            't': [[2, 1, 2, 4, 3, 4, 4, 3], [0, 2, 4, 2]],
            'u': [[0, 2, 0, 3, 1, 4, 3, 4, 4, 3], [4, 2, 4, 4]],
            'v': [[0, 2, 2, 4, 4, 2]],
            'w': [[0, 2, 0, 3, 1, 4, 2, 3, 3, 4, 4, 3, 4, 2], [2, 2, 2, 3]],
            'x': [[0, 2, 4, 4], [4, 2, 0, 4]],
            'y': [[4, 2, 1, 5], [0, 2, 2, 4]],
            'z': [[0, 2, 4, 2, 0, 4, 4, 4]],
            '{': [[3, 0, 2, 0, 1, 1, 2, 2, 1, 3, 2, 4, 3, 4], [0, 2, 2, 2]],
            '|': [[2, 0, 2, 5]],
            '}': [[1, 0, 2, 0, 3, 1, 2, 2, 3, 3, 2, 4, 1, 4], [4, 2, 2, 2]],
            '~': [[0, 1, 1, 0, 2, 1, 3, 1, 4, 0]],
            'µ': [[0.5, 5.5, 0.5, 1, 0.5, 3, 1, 4, 3, 4, 3.5, 3], [3.5, 1, 3.5, 4]]
        }

        self.colors = [
            (255, 0, 0),
            (0, 0, 255),
            (0, 255, 0),
            (0, 255, 255),
            (220, 220, 0),
            (255, 0, 255),
            (64, 0, 255),
            (128, 255, 0),
            (128, 128, 128),
            (255, 0, 128),
            (128, 0, 255),
            (0, 96, 0),
            (0, 0, 96)
        ]

        self.blackAndWhite = blackAndWhite
        self.pageWidth = pageWidth / scale
        self.pageHeight = pageHeight / scale
        pdfWidth = pageWidth / 10
        pdfHeight = pageHeight / 10
        self.pdf = AlphaPDF(orientation='L', unit='in', format=(pdfHeight, pdfWidth))
        self.pdf.add_page()
        self._out('1 J 1 j')  # Set line cap and join styles
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.rotate = False

        self._scale(7.2 * scale)
        self._flipY()
        self._translate(0,-self.pageHeight)
        self.lineWidth(.2)
        self.showNumbers = showNumbers
        self.showTraces = showTraces
        self.showCrosses = showCrosses
        if not showCrosses: self.showTraces = False
        self.showJumpers = showJumpers
        self.showComponents = showComponents
        self.black()

    def dotGrid(self):
        self.lineWidth(0.1)
        for y in range(1, self.pageHeight):
            for x in range(1, self.pageWidth):
                self._line(x,y,x,y)

    def originMark(self):
        self.red()
        self._out('%.2F %.2F m %.2F %.2F l S' % (-1,-1, 1,1))
        self._out('%.2F %.2F m %.2F %.2F l S' % (-1,1, 1,-1))
        self.black()

    def title(self, x, y, text):
        self.showComponents = True
        self.flipX = False
        self._push()
        self._translate((self.pageWidth-len(text)*1.5)/2+x,4+y)
        self._scale(1.5)
        self.text(0,0,text.upper())
        self._pop()

    def partsList(self,x,y,parts):
        self.showComponents = True
        self.showCrosses = True
        self.flipX = False
        self._push()
        width = 0
        height = len(parts) * 1.5 + 6
        for p in parts:
            width = max(width, len(p))
        width += 1
        self._translate((self.pageWidth-width)/2+x, (self.pageHeight-height)/2+y)
        self.black()
        self.text(1,0,'PARTS LIST')
        self.text(1.05,0,'PARTS LIST')
        self.wire(0,1,width,1)
        y = 2
        for p in parts:
            self.text(1,y,p.upper())
            y += 1.5
        self.cut(1,int(y+1))
        self.text(3,int(y+1),"= CUT TRACE")
        self._pop()

    def beginBoard(
        self, boardWidth, boardHeight, 
        rotate=False, 
        at=(0,0),
        showStrips=True, 
        showTraces=True,
        showNumbers=False,
        showCrosses=True,
        showJumpers=True,
        showComponents=True,
        showDrills=True,
        showCoordinates=True,
        flipX=False,
        title=""
    ):
        self.showNumbers = True
        self.showTraces = True
        self.showCrosses = True
        self.showJumpers = True
        self.showComponents = True
        self.showStrips=True
        self.flipX = False
        self.showCoordinates = showCoordinates

        self.connections = []
        self.traceOrigins = []
        self.traceColor = 0
        self.boardWidth = boardWidth
        self.boardHeight = self.row(boardHeight)
        self.rotate = rotate
        boardWidth += 1
        boardHeight = self.row(boardHeight) + 1
        self._push()
        self._translate(self.pageWidth/2 + at[0], self.pageHeight/2 + at[1])
        self._push()
        if rotate:
            self._translate(0, -boardWidth/2)
            self._rotate(90);
            self.vtext(-3,-len(title)/2,title)
        else:
            self._translate(-len(title)/2, -boardHeight/2)
            self.text(0.5,-3,title)
        self._pop()
        self.flipX = flipX
        if flipX: 
            self._flipX()
        if self.rotate: self._rotate(90)
        self._translate(-boardWidth/2, -boardHeight/2)
        self.box(0, 0, boardWidth, boardHeight)
        letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 10)
        for y in range(1, boardHeight):
            if showStrips:
                if not self.blackAndWhite:
                    self.grey(240)
                    self._rect(
                        0.4,y-0.4,
                        (boardWidth - 0.8),0.8,
                        'F'
                    )

            if self.blackAndWhite:
                pass
                for x in range(1, boardWidth):
                    self.black()
                    self._ellipse(x,y,0.02,0.02,'F')
            else:
                self.white()
                for x in range(1, boardWidth):
                    self.dot(x, y, 'F')

            self.grey(220)
            if self.showCoordinates:
                self.text(-1,y,letters[y-1])
                self.text(boardWidth+1,y,letters[y-1])

        if self.showCoordinates:
            for x in range(1, boardWidth):
                if flipX and rotate:
                    self.utext(x, -1, str(x)[::-1])
                    self.vtext(x, boardHeight + 1, str(x)[::-1])
                else:
                    self.utext(x, -1, str(x))
                    self.vtext(x, boardHeight + 1, str(x))
        self.black()
        self.showNumbers = showNumbers
        self.showTraces = showTraces
        self.showCrosses = showCrosses
        if not showCrosses: self.showTraces = False
        self.showJumpers = showJumpers
        self.showComponents = showComponents
        self.showDrills = showDrills

    def endBoard(self):
        self._pop()

    def _out(self,str):
        self.pdf._out(str)

    def _rect(self,x,y,w,h,f='S'):
        self._out('%.2F %.2F m %.2F %.2F l %.2F %.2F l %.2F %.2F l %.2F %.2F l %s' % 
            (x,y, x+w,y, x+w,y+h, x,y+h, x,y, f))

    def _line(self,x1,y1,x2,y2,f='S'):
        self._out('%.2F %.2F m %.2F %.2F l %s' % (x1,y1,x2,y2,f))

    def _ellipse(self,x,y,rx,ry,f='F',tl=True,tr=True,bl=True,br=True):
        kappa = 0.5522848 # 4 * ((√(2) - 1) / 3)
        ox = rx * kappa
        oy = ry * kappa
        xe = x + rx
        ye = y + ry
        self._out('%.2F %.2F m' % (x-rx,y))
        if tl: 
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x-rx,y-oy, x-ox,y-ry, x,y-ry))
        else:
            self._out('%.2F %.2F l %.2F %.2F l' % (x,y,x,y-ry))
        if tr: 
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x+ox,y-ry, xe,y-oy, xe,y))
        else:
            self._out('%.2F %.2F l %.2F %.2F l' % (x,y,xe,y))
        if br: 
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (xe,y+oy, x+ox,ye, x,ye))
        else:
            self._out('%.2F %.2F l %.2F %.2F l' % (x,y,x,ye))
        if bl: 
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x-ox,ye, x-rx,y+oy, x-rx,y))
        else:
            self._out('%.2F %.2F l %.2F %.2F l' % (x,y,x-rx,y))
        self._out(f)

    def _arc(self,x,y,rx,ry,f='S',tl=True,tr=True,bl=True,br=True):
        kappa = 0.5522848 # 4 * ((√(2) - 1) / 3)
        ox = rx * kappa
        oy = ry * kappa
        xe = x + rx
        ye = y + ry
        if tl: 
            self._out('%.2F %.2F m' % (x-rx,y))
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x-rx,y-oy, x-ox,y-ry, x,y-ry))
            self._out(f)
        if tr: 
            self._out('%.2F %.2F m' % (x,y-ry))
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x+ox,y-ry, xe,y-oy, xe,y))
            self._out(f)
        if br: 
            self._out('%.2F %.2F m' % (xe,y))
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (xe,y+oy, x+ox,ye, x,ye))
            self._out(f)
        if bl: 
            self._out('%.2F %.2F m' % (x,ye))
            self._out('%.2F %.2F %.2F %.2F %.2F %.2F c' % (x-ox,ye, x-rx,y+oy, x-rx,y))
            self._out(f)

    def row(self, y):
        if(isinstance(y, str)):
            y = ord(y) - 64
        return y

    def box(self, x, y, w, h, f='S'):
        if not self.showComponents: return
        y = self.row(y)
        self._rect(x,y,w,h,f)

    def wire(self, x, y, x2, y2):
        y = self.row(y)
        y2 = self.row(y2)
        self._line(x,y,x2,y2)

    def vtext(self, x, y, text, scale=0.85):
        if not self.showComponents: return
        y = self.row(y)
        chars = list(text)
        if self.rotate:
            chars.reverse()
        yy = 0
        for c in chars:
            self.drawLetter(x, y + yy, c, scale=scale)
            yy += 1

    def utext(self, x, y, text, scale=0.85):
        if not self.showComponents: return
        y = self.row(y)
        chars = list(text)
        if not self.rotate:
            chars.reverse()
        yy = 0
        for c in chars:
            self.drawLetter(x, y - yy, c, scale=scale)
            yy += 1

    def text(self, x, y, text, scale=0.85):
        if not self.showComponents: return
        y = self.row(y)
        chars = list(text)
        xx = 0
        for c in chars:
            self.drawLetter(x + xx, y, c, scale=scale)
            xx += scale

    def rtext(self, x, y, text, scale=0.85):
        if not self.showComponents: return
        y = self.row(y)
        chars = reversed(list(text))
        xx = 0
        for c in chars:
            self.drawLetter(x + xx, y, c, scale=scale)
            xx -= scale

    def radial(self, x, y, l, upside_down=False):
        y = self.row(y)
        self.jdot(x,y)
        self.jdot(x,y+l)
        r=l/2+0.5
        if self.showComponents: self._ellipse(x,y+(l/2),r,r,f='S')

    def axial(self, x, y, l=1):
        y = self.row(y)
        yy = y - 1.5 + (l/2)
        self.black()
        if self.showComponents:
            self._rect(x-0.4,y-0.4,0.8,l+0.8,f='F')
        self.jdot(x, y)
        self.jdot(x, y + l)

    def cap(self, x, y, l=1, upside_down=False):
        y = self.row(y)
        self.jdot(x,y)
        self.jdot(x,y+l)
        if self.showComponents:
            w = 0.75
            self.wire(x, y, x, y + 0.3)
            self.wire(x, y + l, x, y + 0.7)
            self.wire(x - w, y + 0.3, x + w, y + 0.3)
            self.wire(x - w, y + 0.7, x + w, y + 0.7)
            if upside_down:
                self.wire(x + w - 0.3, y + 1.2, x + w + 0.1, y + 1.2)
                self.wire(x + w - 0.1, y + 1.0, x + w - 0.1, y + 1.4)
            else:
                self.wire(x - 0.2, y - 0.2, x - 0.6, y - 0.2)
                self.wire(x - 0.4, y - 0.0, x - 0.4, y - 0.4)

    def sip(self, x, y, l, name, upside_down=False, pins=None, flip=False, mod=1, width=1, labelScale=1.0):
        y = self.row(y)
        self.box(x - (width / 2), y - 0.5, width, l)
        for yy in range(0, l, mod):
            self.dot(x, y + yy)
        if flip:
            self.vtext(
                x + (width / 2 + 0.7),
                y + (l - len(name)) * 0.5,
                name
            )
        else:
            self.vtext(
                x - (width / 2 + 0.7),
                y + (l - len(name)) * 0.5,
                name
            )
        if upside_down:
            if self.showComponents: self._ellipse(x,y+l-1,0.5,0.5,'S')
            if pins != None:
                p = 0
                for yy in reversed(range(0, l)):
                    if flip:
                        self.rtext((x - 0.4 - labelScale), yy + y, pins[p], scale=labelScale)
                    else:
                        self.text((x + 0.4 + labelScale), yy + y, pins[p], scale=labelScale)
                    p += 1
        else:
            if self.showComponents: self._ellipse(x,y,0.5,0.5,'S')
            if pins != None:
                p = 0
                lp = len(pins)
                for yy in range(0, l):
                    if p < lp:
                        if flip:
                            self.rtext((x - 0.4 - labelScale), yy + y, pins[p], scale=labelScale)
                        else:
                            self.text((x + 0.4 + labelScale), yy + y, pins[p], scale=labelScale)
                    p += 1

    def esp32minikit(self, x, y):
        self.dip(5, 'C', 9, 10, "ESP32", False, [
            '7', '15', '5V', 'G', '16', '17', 'SDA', 'SCL', 'RX', 'TX',
            'RST', '36', '26', 'SCK', 'MISO', 'MOSI', 'CS0', '3V3', '13', '10'
        ],
        labelOffset=0.5,
        labelScale=0.8,
        skipPins=[]
        )
        self.sip(4, 'C', 10, "", False, flip=True, pins=['6', '8', '2', '0', '4', '12', '32', '25', '27', 'GND'], labelScale=0.8)
        self.sip(4, 'C', 10, "", False, flip=True, pins=['6', '8', '2', '0', '4', '12', '32', '25', '27', 'GND'], labelScale=0.8)
        self.sip(15, 'C', 10, "", True, flip=False, pins=['GND', 'NC', '39', '35', '33', '34', '14', 'NC', '9', '11'], labelScale=0.8)
    
    def rp2040(self, x, y):
        # Seeed studio XIAO RP2040 module
        y = self.row(y)
        self.dip(x, y, 6, 7, "RP2040", pins=['D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'TX', 'RX', 'D8', 'D9', 'D10', '3V3', 'GND', '5V'], labelScale=0.6)
        self.box(x+1.5,y-1.5,3,1.2,'F')

    def digispark(self, x, y,showPort=False,groundOnly=False):
        y = self.row(y)
        self.box(x-0.5,y-0.5,8,7)
        self.sip(x,y+1,6,name="",pins=['D','2','C','A','1','R'])
        if groundOnly: self.sip(x+5,y,1,name="",pins=['GND'],flip=True)
        if not groundOnly:
            self.sip(x+3,y,1,name="",pins=['I'],flip=True)
            self.sip(x+4,y,1,name="")
            self.sip(x+5,y,1,name="",pins=['+'])
        if showPort: self.box(x+5,y+1.5,3,3,'F')

    def usbBreakout(self, x, y, showPort=False):
        y = self.row(y)
        self.box(x-0.5,y-0.5,6,5)
        self.sip(x,y,5,name="",pins=['G','ID','D+','D-','5V'])
        if showPort: self.box(x+3.5,y+0.5,2,3,'F')

    def white(self):
        self.pdf.set_draw_color(255)
        self.pdf.set_fill_color(255)
        self.lastColor = (255,255,255)

    def black(self):
        self.pdf.set_draw_color(0)
        self.pdf.set_fill_color(0)
        self.lastColor = (0,0,0)

    def grey(self,l=128):
        if self.blackAndWhite:
            self.black()
            self.lastColor = (0,0,0)
        else:
            self.pdf.set_draw_color(l)
            self.pdf.set_fill_color(l)
            self.lastColor = (l,l,l)

    def red(self):
        self.pdf.set_draw_color(255,0,0)
        self.pdf.set_fill_color(255,0,0)
        self.lastColor = (255,0,0)
    
    def blue(self):
        self.pdf.set_draw_color(16, 128, 255)
        self.pdf.set_fill_color(16, 128, 255)
        self.lastColor = (16, 128, 255)
    
    def green(self):
        self.pdf.set_draw_color(16, 180, 16)
        self.pdf.set_fill_color(16, 180, 16)
        self.lastColor = (16, 180, 16)

    def color(self,r,g=0,b=0):
        if type(r) == tuple:
            g = r[1]
            b = r[2]
            r = r[0]
        self.pdf.set_draw_color(r,g,b)
        self.pdf.set_fill_color(r,g,b)
        self.lastColor = (r,g,b)

    def power(self, x, y,upside_down=False):
        y = self.row(y)
        if upside_down:
            self.box(x-2,y-0.5,3.5,5)
            self.text(x+1,y+2,'-')
            self.drill(x,y+2)
            self.drill(x-2,y+1)
            self.drill(x,y)
            self.text(x+1,y,'+')
            self.text(x-1,y+1,'S')
        else:
            self.box(x-2,y-4.5,3.5,5)
            self.text(x+1,y-2,'-')
            self.drill(x,y-2)
            self.drill(x-2,y-1)
            self.drill(x,y)
            self.text(x+1,y,'+')
            self.text(x-1,y-1,'S')

    def shroud(self,x,y,l=8):
        y = self.row(y)
        self.box(x-1,y-2,3,l+3,'F')
        self.header(x,y,l)
        self.header(x+1,y,l)
        self.white()
        self.box(x+1.7,y-2+(l+1)/2,0.35,2,'F')
        self.black()

    def dip(self, x, y, w, h, name="", upside_down=False, pins=None, labelsInside=True, labelOffset=0, labelScale=0.78, mod=1, skipPins=[]):
        y = self.row(y)

        self.box(x + 0.5, y - 0.5, w - 1, h)
        for yy in range(0, h, mod):
            skipPin = yy+1 in skipPins
            if not skipPin:
                if self.showComponents: self.wire(x, y + yy, x + 0.5, y + yy)
                self.dot(x, y + yy)
        for yy in range(h-1, -1, -mod):
            if not h*2-yy in skipPins:
                if self.showComponents: self.wire(x + w, y + yy, x + w - 0.5, y + yy)
                self.dot(x + w, y + yy)


        if upside_down:
            if self.showComponents: self._ellipse(x + w, y + h - 1, 0.5, 0.5, 'S')
            if pins != None:
                p = 0
                for yy in reversed(range(0, h, mod)):
                    if labelsInside:
                        self.rtext((x + w - labelScale - 0.3), yy + y, pins[p], scale=labelScale)
                    else:
                        self.text((x + w + labelScale + 0.3), yy + y, pins[p], scale=labelScale)
                    p += 1
                for yy in range(0, h, mod):
                    if labelsInside:
                        self.text((x + labelScale + 0.3), yy + y, pins[p], scale=labelScale)
                    else:
                        self.rtext((x - labelScale - 0.3), yy + y, pins[p], scale=labelScale)
                    p += 1
        else:
            if self.showComponents: self._ellipse(x,y,0.5,0.5,'S')
            if pins != None:
                p = 0
                lp = len(pins)
                for yy in range(0, h, mod):
                    if p < lp:
                        if labelsInside:
                            self.text((x + labelScale + 0.3), yy + y, pins[p], scale=labelScale)
                        else:
                            self.rtext((x - labelScale - 0.1), yy + y, pins[p], scale=labelScale)
                    p += 1
                for yy in reversed(range(0, h, mod)):
                    if p < lp:
                        if labelsInside:
                            self.rtext((x + w - labelScale - 0.3), yy + y, pins[p], scale=labelScale)
                        else:
                            self.text((x + w + labelScale + 0.1), yy + y, pins[p], scale=labelScale)
                    p += 1

        if self.blackAndWhite:
            if name != '':
                self.black()
                xx = x + math.floor(w / 2) + labelOffset
                self.box(xx - 0.5, y - 0.5, 1, h, f='F')
                self.white()
                self.vtext(xx, y + (h - len(name)) * 0.5, name)
                self.black()
        else:
            self.pdf.set_draw_color(255)
            self.pdf.set_fill_color(128)
            self.pdf.set_alpha(1.0)
            if name != '':
                xx = x + math.floor(w / 2) + labelOffset
                self.box(xx - 0.5, y - 0.5, 1, h, f='F')
                self.pdf.set_alpha(1)
                self.vtext(xx, y + (h - len(name)) * 0.5, name)
            self.pdf.set_alpha(1)
            self.pdf.set_draw_color(0)
            self.pdf.set_fill_color(0)

    def offRight(self, x, y, text):
        if not self.showComponents: return
        y = self.row(y)
        x2 = self.boardWidth+1

        self.dot(x, y)
        self.blue()
        self.wire(x,y,x2,y)
        self.polyline([
            x2,y,
            x2+0.5,y-0.5,
            x2+0.7+len(text),y-0.5,
            x2+0.7+len(text),y+0.5,
            x2+0.5,y+0.5,
            x2,y
        ],'F')
        self.white()
        self.text(x2+1,y,text)
        self.black()


    def pot(self, x, y, upside_down=False):
        y = self.row(y)
        self.dot(x, y + 0)
        self.dot(x, y + 1)
        self.dot(x, y + 2)
        if not self.showComponents: return
        if upside_down:
            self.box(x - 5, y - 1, 4, 4)
            self.wire(x, y, x - 1, y)
            self.wire(x, y + 1, x - 1, y + 1)
            self.wire(x, y + 2, x - 1, y + 2)

            self.cut(x - 3, y - 1)
            self.cut(x - 3, y + 3)
            self._ellipse(x - 3,y + 1,1,1,'F')
            self.pdf.set_draw_color(255)
            self.wire(x - 3, y + 1, x - 4, y + 1)
            self.pdf.set_draw_color(0)
            self._ellipse(x - 3, y + 1, 1.3, 1.3, 'S')
        else:
            self.box(x + 1, y - 1, 4, 4)
            self.wire(x, y, x + 1, y)
            self.wire(x, y + 1, x + 1, y + 1)
            self.wire(x, y + 2, x + 1, y + 2)
            self.cut(x + 3, y - 1)
            self.cut(x + 3, y + 3)
            self._ellipse(x + 3,y + 1,1,1,'F')
            self.pdf.set_draw_color(255)
            self.wire(x + 3, y + 1, x + 4, y + 1)
            self.pdf.set_draw_color(0)
            self._ellipse(x + 3, y + 1, 1.3, 1.3, 'S')

    def jack(self, x, y, upside_down=False):
        y = self.row(y)
        if upside_down:
            if self.showComponents:
                self._rect(x-1.5,y-0.5,3,4,'F')
                self.text(x+1,y+4,'R')
                self.white()
                self.text(x+1,y+3,'S')
                self.text(x+1,y,'T')
                self._ellipse(x,y+1.5,1,1)
                self.black()
                self._ellipse(x,y+1.5,0.75,0.75)
            self.jdot(x, y)
            self.jdot(x, y + 3)
            self.jdot(x, y + 4)
        else:
            if self.showComponents:
                self._rect(x-1.5,y+0.5,3,4,'F')
                self.text(x+1,y,'R')
                self.white()
                self.text(x+1,y+1,'S')
                self.text(x+1,y+4,'T')
                self._ellipse(x,y+2.5,1,1)
                self.black()
                self._ellipse(x,y+2.5,0.75,0.75)
            self.jdot(x, y)
            self.jdot(x, y + 1)
            self.jdot(x, y + 4)

    def header(self, x, y, h):
        y = self.row(y)
        if self.showComponents:
            self._rect(
                x-0.5,
                y-0.6,
                (1),
                (h + 0.2),
                'F'
            )
            self.white()
            for yy in range(y, y + h):
                self.dot(x, yy, 'F')
            self.black()
        elif self.showCrosses:
            self.black()
            for yy in range(y, y + h):
                self.dot(x, yy, 'F')

    def hheader(self, x, y, w):
        y = self.row(y)
        if self.showComponents:
            self._rect(
                x-0.5,
                y-0.4,
                ((w+1) * 0.8),
                (0.8),
                'F'
            )
            self.white()
            for xx in range(x, x + w):
                self.dot(xx, y, 'F')
            self.black()
            for xx in range(x, x + w - 1):
                self.cut(xx+0.5,y)
        elif self.showCrosses:
            self.black()
            for xx in range(x, x + w):
                self.dot(xx, y, 'F')
            for xx in range(x, x + w - 1):
                self.cut(xx+0.5,y)

    def hres(self, x, y, val,l=4):
        y = self.row(y)
        if self.showComponents:
            self.dot(x, y)
            self.wire(x, y, x + 0.4, y)
            self.box(x + 0.4, y - 0.5, l + 0.2, 1, 'F')
        self.cut(x + 1, y)
        if self.showComponents:
            self.wire(x + l +0.6, y, x + l + 1, y)
            self.dot(x + l + 1, y)
            self.white()
            self.text(x + 1, y, val)
            self.black()

    def bigButton(self, x, y):
        
        y = self.row(y)
        self.dot(x, y)
        if self.showComponents: self.wire(x, y, x + 0.5, y)
        self.dot(x, y + 2)
        if self.showComponents: self.wire(x, y + 2, x + 0.5, y + 2)
        self.dot(x + 5, y)
        if self.showComponents: self.wire(x + 5, y, x + 5 - 0.5, y)
        self.dot(x + 5, y + 2)
        if self.showComponents: self.wire(x + 5, y + 2, x + 5 - 0.5, y + 2)
        if self.showComponents: self.box(x + 0.5, y - 1, 4, 4)
        if self.showComponents: self._ellipse(x + 2.5, y + 1, 1.5, 1.5)

    def button(self, x, y):
        y = self.row(y)
        self.dot(x,y)
        if self.showComponents: self.wire(x,y,x+0.5,y)
        self.dot(x+3,y)
        if self.showComponents: self.wire(x+3,y,x+2.5,y)
        self.dot(x,y+2)
        if self.showComponents: self.wire(x,y+2,x+0.5,y+2)
        self.dot(x+3,y+2)
        if self.showComponents: self.wire(x+3,y+2,x+2.5,y+2)
        if self.showComponents: self.box(x+0.5,y,2,2)
        if self.showComponents: self._ellipse(x+1.5,y+1,0.75,0.75)

    def led(self, x, y, upside_down=False, len=1, weight=0.5):
        y = self.row(y)
        if self.showComponents or self.showCrosses:
            self.dot(x, y)
            self.dot(x, y + len)
        if self.showComponents:
            yy = y + ((len-1)*weight)
            self.wire(x,y,x,yy)
            self.wire(x,yy+1.0,x,y+len)

            self._ellipse(x, yy+0.5, 0.75, 0.75, 'S')
            if upside_down:
                self.wire(x - 0.5, yy + 0.8, x + 0.5, yy + 0.8)
                self.wire(x - 0.5, yy + 0.8, x, yy + 0.2)
                self.wire(x + 0.5, yy + 0.8, x, yy + 0.2)
                self.wire(x - 0.5, yy + 0.2, x + 0.5, yy + 0.2)
            else:
                self.wire(x - 0.5, yy + 0.2, x + 0.5, yy + 0.2)
                self.wire(x - 0.5, yy + 0.2, x, yy + 0.8)
                self.wire(x + 0.5, yy + 0.2, x, yy + 0.8)
                self.wire(x - 0.5, yy + 0.8, x + 0.5, yy + 0.8)

    def diode(self, x, y, upside_down=False, len=1):
        if not self.showComponents: return
        y = self.row(y)
        self.dot(x, y)
        self.dot(x, y + len)
        yy = y - 0.5 + (len/2)
        self.wire(x,y,x,yy)
        self.wire(x,yy+1.0,x,y+len)

        self.wire(x - 0.5, yy + 0.2, x + 0.5, yy + 0.2)
        self.wire(x - 0.5, yy + 0.2, x, yy + 0.8)
        self.wire(x + 0.5, yy + 0.2, x, yy + 0.8)
        self.wire(x - 0.5, yy + 0.8, x + 0.5, yy + 0.8)

    def zener(self, x, y, upside_down=False, len=1):
        if not self.showComponents: return
        y = self.row(y)
        self.dot(x, y)
        self.dot(x, y + len)
        yy = y - 0.5 + (len/2)
        self.wire(x,y,x,yy)
        self.wire(x,yy+1.0,x,y+len)
        if upside_down:
            self.wire(x - 0.5, yy + 0.8, x + 0.5, yy + 0.8 )
            self.wire(x - 0.5, yy + 0.8, x      , yy + 0.2 )
            self.wire(x + 0.5, yy + 0.8, x      , yy + 0.2 )
            self.wire(x - 0.5, yy + 0.2, x + 0.5, yy + 0.2 )
            self.wire(x - 0.5, yy + 0.2, x - 0.5, yy + 0.0 )
            self.wire(x + 0.5, yy + 0.2, x + 0.5, yy + 0.4 )
        else:
            self.wire(x - 0.5, yy + 0.2, x + 0.5, yy + 0.2 )
            self.wire(x - 0.5, yy + 0.2, x      , yy + 0.8 )
            self.wire(x + 0.5, yy + 0.2, x      , yy + 0.8 )
            self.wire(x - 0.5, yy + 0.8, x + 0.5, yy + 0.8 )
            self.wire(x - 0.5, yy + 0.8, x - 0.5, yy + 0.6 )
            self.wire(x + 0.5, yy + 0.8, x + 0.5, yy + 1.0 )

    def resist(self, x, y, val='', upside_down=False, l=1):
        y = self.row(y)
        yy = y - 1.5 + (l/2)
        self.black()
        if l <= 2:
            if self.showComponents:
                self._rect(x-0.4,y-0.4,0.8,l+0.8,f='F')
            self.jdot(x, y)
            self.jdot(x, y + l)
        else:
            if self.showComponents: 
                self._rect(x-0.5,yy,1,3,f='F')
            self.jdot(x, y)
            self.jdot(x, y + l)
            if self.showComponents: 
                self.wire(x,y,x,yy)
                self.wire(x,yy+3.0,x,y+l)
        if self.showComponents: 
            self.white()
            if l >= len(val): self.vtext(x,yy+2-(len(val)/2),val)
        self.black()

    def part2pin(self, x, y, val='', upside_down=False, l=1):
        y = self.row(y)
        if self.showComponents:
            yy = y
            self.black()
            self._rect(x-0.4,yy,0.8,l,f='F')
            self.jdot(x, y)
            self.jdot(x, y + l)
            self.white()
            self.vtext(x,yy+2-(len(val)/2),val)
            self.black()
        elif self.showCrosses:
            self.jdot(x, y)
            self.jdot(x, y + l)

    def t3904(self, x, y, upside_down=False):
        if not self.showComponents: return
        y = self.row(y)
        self.grey(160)
        if upside_down:
            self._ellipse(x-0.2,y,1.2,1.2,'F',tl=False,bl=False)
        else:
            self._ellipse(x-0.2,y,1.2,1.2,'F',tr=False,br=False)
        self.black()
        if upside_down:
            self.text(x+1, y-1, 'E')
        else:
            self.text(x+1, y-1, 'C')
        self.jdot(x, y-1)
        self.text(x-1, y, 'B')
        self.jdot(x, y)
        if upside_down:
            self.text(x+1, y+1, 'C')
        else:
            self.text(x+1, y+1, 'E')
        self.jdot(x, y+1)

    def dot(self, x, y, f='F'):
        y = self.row(y)
        if self.showComponents:
            self._ellipse(x,y,0.25,0.25,f)
        elif self.showCrosses:
            self._ellipse(x,y,0.1,0.1,f)

    def jdot(self, x, y, f='F'):
        y = self.row(y)
        if self.showJumpers:
            self.white()
            self._ellipse(x,y,0.35,0.35,f)
            self.black()
            self._ellipse(x,y,0.25,0.25,f)
        elif self.showCrosses:
            self.black()
            self._ellipse(x,y,0.1,0.1,f)   
        else:
            self.white()
            self._ellipse(x,y,0.2,0.2,f)   
            self.black()
            self._ellipse(x,y,0.15,0.15,f)   

    def drill(self, x, y):
        if not self.showDrills: return
        y = self.row(y)
        self._ellipse(x,y,0.25,0.25,'F')
        self._ellipse(x,y,0.5,0.5,'S')

    def cut(self, x, y, y2=None):
        if not self.showCrosses: return
        y = self.row(y)
        if y2 == None:
            y2 = y
        y2 = self.row(y2)
        xx = x
        self.pdf.set_draw_color(255, 0, 0)
        r = 0.3
        for yy in range(int(y), int(y2) + 1):
            self.connections.append((False, x, yy))
            yyy = yy
            if x != math.floor(x):
                self._line(
                    (xx),
                    (yyy - 0.5),
                    (xx),
                    (yyy + 0.5)
                )
            else:
                self._line(
                    (xx - r),
                    (yyy - r),
                    (xx + r),
                    (yyy + r)
                )
                self._line(
                    (xx - r),
                    (yyy + r),
                    (xx + r),
                    (yyy - r)
                )
        self.pdf.set_draw_color(0)

    def drawCuts(self):
        self.pdf.set_draw_color(255, 0, 0)
        r = 0.3
        for con in self.connections:
            if not con[0]:  # Cut
                xx = con[1]
                yyy = con[2]
                if xx != math.floor(xx):
                    # Cut
                    self._line(
                        (xx),
                        (yyy - 0.5),
                        (xx),
                        (yyy + 0.5)
                    )
                else:
                    # Cross
                    self._line(
                        (xx - r),
                        (yyy - r),
                        (xx + r),
                        (yyy + r)
                    )
                    self._line(
                        (xx - r),
                        (yyy + r),
                        (xx + r),
                        (yyy - r)
                    )
        self.pdf.set_draw_color(0)

    def jumper(self, x, y, x2, y2, color=(16, 128, 255), showLength=True):
        y = self.row(y)
        if self.showJumpers:
            if(isinstance(y2, str)):
                y2 = ord(y2) - 64
            self.connections.append((True, x, y, x2, y2))
            self.connections.append((True, x2, y2, x, y))
        self.jdot(x, y)
        self.jdot(x2, y2)
        if self.showJumpers:
            if self.blackAndWhite:
                self.black()
                self.lineWidth(.05)
            else:
                self.pdf.set_draw_color(*color)
            self.wire(x, y, x2, y2)

            dist = int(((x2 - x)**2 + (y2 - y)**2)**0.5)
            if dist > 2 and self.showNumbers and showLength:
                dist = str(dist)
                self.pdf.set_fill_color(255)
                self._rect(
                    (x-0.5) + (x2 - x) / 2,
                    (y-0.5) + (y2 - y) / 2,
                    1,
                    len(dist),
                    "F"
                )
                if self.blackAndWhite:
                    self.black()
                else:
                    self.pdf.set_draw_color(*color)
                self.vtext(x + (x2 - x) / 2, y + (y2 - y) / 2, dist)
            if self.blackAndWhite:
                self.lineWidth(.2)

        self.pdf.set_draw_color(0)
        self.pdf.set_fill_color(0)

    def terminal(self,x,y,h,mod=1,shroudYOffset=0):
        y = self.row(y)
        if self.showComponents:
            self._rect(
                x-1,
                y-0.4+shroudYOffset,
                (2.5),
                (h - 0.2),
                'F'
            )
            self.white()
            for yy in range(y, y + h, mod):
                self.dot(x, yy, 'F')
            self.black()
        elif self.showCrosses:
            self.black()
            for yy in range(y, y + h):
                self.dot(x, yy, 'F')

    def bus(self, x, y1, y2):
        for i in range(y1, y2-1):
            self.jumper(x,i,x,i+1)
        self.jumper(x,y1,x,y2,showLength=False)

    def traceJumper(self, x, y, x2, y2, color):
        if not self.showJumpers: return
        y = self.row(y)
        if(isinstance(y2, str)):
            y2 = ord(y2) - 64
        self.jdot(x, y)
        self.jdot(x2, y2)
        self.pdf.set_draw_color(*color)
        self.wire(x, y, x2, y2)

        dist = int(((x2 - x)**2 + (y2 - y)**2)**0.5)
        if dist > 2 and self.showNumbers:
            dist = str(dist)
            self.pdf.set_fill_color(255)
            self._rect(
                (x + (x2 - x) / 2)-0.5,
                (y + (y2 - y) / 2)-0.5,
                1,
                len(dist),
                "F"
            )
            self.pdf.set_draw_color(*color)
            self.vtext(x + (x2 - x) / 2, y + (y2 - y) / 2, dist)

        self.pdf.set_draw_color(*color)
        self.pdf.set_fill_color(0)

    def trace(self, x, y, color=None):
        if not self.showTraces: return
        y = self.row(y)
        marked = []
        if color == None:
            color = self.colors[self.traceColor]
        self.tracePoint(x, y, marked, color, first=True)
        self.pdf.set_draw_color(0)
        self.pdf.set_fill_color(0)
        self.traceColor = (self.traceColor + 1) % len(self.colors)

    def tracePoint(self, x, y, marked, color, first=False):
        for mark in marked:
            if mark[0] == x and mark[1] == y:
                return
        marked.append((x, y))
        foundLeftSlice = False
        foundRightSlice = False
        for con in self.connections:
            if con[1] == x and con[2] == y:
                if con[0]:  # Jumper
                    self.traceJumper(con[1], con[2], con[3], con[4], color)
                    self.tracePoint(con[3], con[4], marked, color)
                else:  # Cross
                    return
            if con[1] == x + 0.5 and con[2] == y:
                foundRightSlice = True
            if con[1] == x - 0.5 and con[2] == y:
                foundLeftSlice = True
        error = False
        for origin in self.traceOrigins:
            if origin[0] == x and origin[1] == y:
                print("Collision! x=%d y=%d" % (x,y))
                error = True
                break
        if first:
            self.traceOrigins.append((x,y))
        if x > 1 and not foundLeftSlice:
            self.tracePoint(x - 1, y, marked, color)
        if x < self.boardWidth+10 and not foundRightSlice:
            self.tracePoint(x + 1, y, marked, color)
        if x <= self.boardWidth:
            self.pdf.set_draw_color(*color)
            self.pdf.set_fill_color(*color)
            if first:
                self.pdf.set_alpha(0.7)
                #self._ellipse(x,y,0.5,0.5)
                self.pdf.set_alpha(1.0)
                #self.white()
                self._rect(x-0.5,y-0.5,1,1,'S')
            else:
                self.pdf.set_alpha(0.45)
                self._rect(x-0.5,y-0.5,1,1,'F')

            self.pdf.set_alpha(1.0)

    def polyline(self, poly, f='S'):
        pdf = self.pdf
        for i in range(0, len(poly), 2):
            if i == 0:
                pdf._out(
                    '%.2f %.2f m ' % (poly[i + 0],poly[i + 1])
                )
            else:
                pdf._out(
                    '%.2f %.2f l ' % (poly[i + 0],poly[i + 1])
                )
        pdf._out(f)

    def copyright(self,x,y):
        if not self.showComponents: return
        y = self.row(y)
        self.lineWidth(0.15)
        self._push()
        self._translate(x,y)
        self._ellipse(0,0,0.4,0.4,'S')
        self._rotate(45)
        self._arc(0,0,0.18,0.18,tl=False)
        self._pop()
        self.lineWidth(0.2)


    def drawLetter(self, x, y, c, scale=1.0):
        xs = 0.8 / 5
        ys = 0.8 / 5
        y = self.row(y)
        xx = x - 0.31
        yy = y - 0.31

        self.lineWidth(0.15)
        v = self.vectorChars[c]
        self._push()
        self._translate(x,y)
        self._scale(scale,scale)
        if self.rotate:
            self._rotate(-90)
        if self.flipX:
            self._flipX()
        lastColor = self.lastColor
        if self.blackAndWhite:
            if self.lastColor == (255,255,255):
                self.black()
            else:
                self.white()
            self.box(-0.5,-0.5,1.0,1.0,'F')
            self.color(lastColor)
        for poly in v:
            line = []
            for i in range(0, len(poly), 2):
                line.append(poly[i + 0] * xs - 0.31)
                line.append(poly[i + 1] * ys - 0.31)
            self.polyline(line)
        self._pop()
        self.lineWidth(0.2)

    def gen(self, pdfName):
        self.pdf.output(pdfName)

    def genCarrier(self, stlName, boardThickness=1.7, nozzle=0.7, rotate=False):
        boardWidth = self.boardWidth
        boardHeight = self.boardHeight
        if rotate:
            boardHeight = self.boardWidth
            boardWidth = self.boardHeight
        cmd = f"openscad /Users/samw3/prj/Make/stripboard/Carrier.scad -D columns={boardWidth} -D rows={boardHeight} -D boardThickness={boardThickness} -D nozzle={nozzle} -o {stlName}"
        # print(cmd)
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
        output, error = process.communicate()

    def _push(self):
        self._out('q')

    def _pop(self):
        self._out('Q')

    def _translate(self, x, y):
        self._out('1 0 0 1 %.2F %.2F cm' % (x,y));

    def _rotate(self, angle):
        angle = angle * 3.1415/180;
        c = math.cos(angle);
        s = math.sin(angle);
        self._out('%.5F %.5F %.5F %.5F 0 0 cm' % (c,s,-s,c));

    def _flipY(self):
        self._out('1 0 0 -1 0 0 cm');

    def _flipX(self):
        self._out('-1 0 0 1 0 0 cm');

    def _scale(self, scaleX, scaleY=None):
        if scaleY==None: scaleY = scaleX
        self._out('%.5F 0 0 %.5F 0 0 cm' % (scaleX, scaleY));

    def lineWidth(self, w):
        self._out('%.2F w' % (w))

