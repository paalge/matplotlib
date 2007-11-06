"""
This module contains all the 2D line class which can draw with a
variety of line styles, markers and colors
"""

# TODO: expose cap and join style attrs
from __future__ import division

import numpy as npy

from matplotlib.numerix import npyma as ma
from matplotlib import verbose
import artist
from artist import Artist
from cbook import iterable, is_string_like, is_numlike
from colors import colorConverter
from path import Path
from transforms import Affine2D, Bbox, TransformedPath

from matplotlib import rcParams

# special-purpose marker identifiers:
(TICKLEFT, TICKRIGHT, TICKUP, TICKDOWN,
    CARETLEFT, CARETRIGHT, CARETUP, CARETDOWN) = range(8)

# COVERAGE NOTE: Never called internally or from examples
def unmasked_index_ranges(mask, compressed = True):
    '''
    Calculate the good data ranges in a masked 1-D npy.array, based on mask.

    Returns Nx2 npy.array with each row the start and stop indices
    for slices of the compressed npy.array corresponding to each of N
    uninterrupted runs of unmasked values.
    If optional argument compressed is False, it returns the
    start and stop indices into the original npy.array, not the
    compressed npy.array.
    Returns None if there are no unmasked values.

    Example:

    y = ma.array(npy.arange(5), mask = [0,0,1,0,0])
    #ii = unmasked_index_ranges(y.mask())
    ii = unmasked_index_ranges(ma.getmask(y))
        # returns [[0,2,] [2,4,]]

    y.compressed().filled()[ii[1,0]:ii[1,1]]
        # returns npy.array [3,4,]
        # (The 'filled()' method converts the masked npy.array to a numerix npy.array.)

    #i0, i1 = unmasked_index_ranges(y.mask(), compressed=False)
    i0, i1 = unmasked_index_ranges(ma.getmask(y), compressed=False)
        # returns [[0,3,] [2,5,]]

    y.filled()[ii[1,0]:ii[1,1]]
        # returns npy.array [3,4,]

    '''
    m = npy.concatenate(((1,), mask, (1,)))
    indices = npy.arange(len(mask) + 1)
    mdif = m[1:] - m[:-1]
    i0 = npy.compress(mdif == -1, indices)
    i1 = npy.compress(mdif == 1, indices)
    assert len(i0) == len(i1)
    if len(i1) == 0:
        return None
    if not compressed:
        return npy.concatenate((i0[:, npy.newaxis], i1[:, npy.newaxis]), axis=1)
    seglengths = i1 - i0
    breakpoints = npy.cumsum(seglengths)
    ic0 = npy.concatenate(((0,), breakpoints[:-1]))
    ic1 = breakpoints
    return npy.concatenate((ic0[:, npy.newaxis], ic1[:, npy.newaxis]), axis=1)

def segment_hits(cx,cy,x,y,radius):
    """Determine if any line segments are within radius of a point. Returns
    the list of line segments that are within that radius.
    """
    # Process single points specially
    if len(x) < 2:
        res, = npy.nonzero( (cx - x)**2 + (cy - y)**2 <= radius**2 )
        return res

    # We need to lop the last element off a lot.
    xr,yr = x[:-1],y[:-1]

    # Only look at line segments whose nearest point to C on the line
    # lies within the segment.
    dx,dy = x[1:]-xr, y[1:]-yr
    Lnorm_sq = dx**2+dy**2    # Possibly want to eliminate Lnorm==0
    u = ( (cx-xr)*dx + (cy-yr)*dy )/Lnorm_sq
    candidates = (u>=0) & (u<=1)
    #if any(candidates): print "candidates",xr[candidates]

    # Note that there is a little area near one side of each point
    # which will be near neither segment, and another which will
    # be near both, depending on the angle of the lines.  The
    # following radius test eliminates these ambiguities.
    point_hits = (cx - x)**2 + (cy - y)**2 <= radius**2
    #if any(point_hits): print "points",xr[candidates]
    candidates = candidates & ~point_hits[:-1] & ~point_hits[1:]

    # For those candidates which remain, determine how far they lie away
    # from the line.
    px,py = xr+u*dx,yr+u*dy
    line_hits = (cx-px)**2 + (cy-py)**2 <= radius**2
    #if any(line_hits): print "lines",xr[candidates]
    line_hits = line_hits & candidates
    points, = point_hits.ravel().nonzero()
    lines, = line_hits.ravel().nonzero()
    #print points,lines
    return npy.concatenate((points,lines))

class Line2D(Artist):
    lineStyles = _lineStyles =  { # hidden names deprecated
        '-'          : '_draw_solid',
        '--'         : '_draw_dashed',
        '-.'         : '_draw_dash_dot',
        ':'          : '_draw_dotted',
        'steps'      : '_draw_steps_pre',
        'steps-mid'  : '_draw_steps_mid',
        'steps-pre'  : '_draw_steps_pre',
        'steps-post' : '_draw_steps_post',
        'None'       : '_draw_nothing',
        ' '          : '_draw_nothing',
        ''           : '_draw_nothing',
    }

    markers = _markers =  {  # hidden names deprecated
        '.'  : '_draw_point',
        ','  : '_draw_pixel',
        'o'  : '_draw_circle',
        'v'  : '_draw_triangle_down',
        '^'  : '_draw_triangle_up',
        '<'  : '_draw_triangle_left',
        '>'  : '_draw_triangle_right',
        '1'  : '_draw_tri_down',
        '2'  : '_draw_tri_up',
        '3'  : '_draw_tri_left',
        '4'  : '_draw_tri_right',
        's'  : '_draw_square',
        'p'  : '_draw_pentagon',
        'h'  : '_draw_hexagon1',
        'H'  : '_draw_hexagon2',
        '+'  : '_draw_plus',
        'x'  : '_draw_x',
        'D'  : '_draw_diamond',
        'd'  : '_draw_thin_diamond',
        '|'  : '_draw_vline',
        '_'  : '_draw_hline',
        TICKLEFT    : '_draw_tickleft',
        TICKRIGHT   : '_draw_tickright',
        TICKUP      : '_draw_tickup',
        TICKDOWN    : '_draw_tickdown',
        CARETLEFT   : '_draw_caretleft',
        CARETRIGHT  : '_draw_caretright',
        CARETUP     : '_draw_caretup',
        CARETDOWN   : '_draw_caretdown',
        'None' : '_draw_nothing',
        ' ' : '_draw_nothing',
        '' : '_draw_nothing',
    }

    filled_markers = ('o', '^', 'v', '<', '>', 's', 'd', 'D', 'h', 'H', 'p')

    zorder = 2
    validCap = ('butt', 'round', 'projecting')
    validJoin =   ('miter', 'round', 'bevel')

    def __str__(self):
        if self._label != "":
            return "Line2D(%s)"%(self._label)
        elif len(self._x) > 3:
            return "Line2D((%g,%g),(%g,%g),...,(%g,%g))"\
                %(self._x[0],self._y[0],self._x[0],self._y[0],self._x[-1],self._y[-1])
        else:
            return "Line2D(%s)"\
                %(",".join(["(%g,%g)"%(x,y) for x,y in zip(self._x,self._y)]))

    def __init__(self, xdata, ydata,
                 linewidth       = None, # all Nones default to rc
                 linestyle       = None,
                 color           = None,
                 marker          = None,
                 markersize      = None,
                 markeredgewidth = None,
                 markeredgecolor = None,
                 markerfacecolor = None,
                 antialiased     = None,
                 dash_capstyle   = None,
                 solid_capstyle  = None,
                 dash_joinstyle  = None,
                 solid_joinstyle = None,
                 pickradius      = 5,
                 **kwargs
                 ):
        """
        Create a Line2D instance with x and y data in sequences xdata,
        ydata

        The kwargs are Line2D properties:
          alpha: float
          animated: [True | False]
          antialiased or aa: [True | False]
          clip_box: a matplotlib.transform.Bbox instance
          clip_on: [True | False]
          color or c: any matplotlib color
          dash_capstyle: ['butt' | 'round' | 'projecting']
          dash_joinstyle: ['miter' | 'round' | 'bevel']
          dashes: sequence of on/off ink in points
          data: (npy.array xdata, npy.array ydata)
          figure: a matplotlib.figure.Figure instance
          label: any string
          linestyle or ls: [ '-' | '--' | '-.' | ':' | 'steps' | 'steps-pre' | 'steps-mid' | 'steps-post' | 'None' | ' ' | '' ]
          linewidth or lw: float value in points
          lod: [True | False]
          marker: [ '+' | ',' | '.' | '1' | '2' | '3' | '4'
          markeredgecolor or mec: any matplotlib color
          markeredgewidth or mew: float value in points (default 5)
          markerfacecolor or mfc: any matplotlib color
          markersize or ms: float
          pickradius: mouse event radius for pick items in points (default 5)
          solid_capstyle: ['butt' | 'round' |  'projecting']
          solid_joinstyle: ['miter' | 'round' | 'bevel']
          transform: a matplotlib.transform transformation instance
          visible: [True | False]
          xdata: npy.array
          ydata: npy.array
          zorder: any number
        """
        Artist.__init__(self)

        #convert sequences to numeric arrays
        if not iterable(xdata):
            raise RuntimeError('xdata must be a sequence')
        if not iterable(ydata):
            raise RuntimeError('ydata must be a sequence')

        if linewidth is None   : linewidth=rcParams['lines.linewidth']

        if linestyle is None   : linestyle=rcParams['lines.linestyle']
        if marker is None      : marker=rcParams['lines.marker']
        if color is None       : color=rcParams['lines.color']
        if markeredgecolor is None :
            markeredgecolor='auto'
        if markerfacecolor is None :
            markerfacecolor='auto'
        if markeredgewidth is None :
            markeredgewidth=rcParams['lines.markeredgewidth']

        if markersize is None  : markersize=rcParams['lines.markersize']
        if antialiased is None : antialiased=rcParams['lines.antialiased']
        if dash_capstyle is None : dash_capstyle=rcParams['lines.dash_capstyle']
        if dash_joinstyle is None : dash_joinstyle=rcParams['lines.dash_joinstyle']
        if solid_capstyle is None : solid_capstyle=rcParams['lines.solid_capstyle']
        if solid_joinstyle is None : solid_joinstyle=rcParams['lines.solid_joinstyle']

        self.set_dash_capstyle(dash_capstyle)
        self.set_dash_joinstyle(dash_joinstyle)
        self.set_solid_capstyle(solid_capstyle)
        self.set_solid_joinstyle(solid_joinstyle)


        self.set_linestyle(linestyle)
        self.set_linewidth(linewidth)
        self.set_color(color)
        self.set_marker(marker)
        self.set_antialiased(antialiased)
        self.set_markersize(markersize)
        self._dashSeq = None


        self.set_markerfacecolor(markerfacecolor)
        self.set_markeredgecolor(markeredgecolor)
        self.set_markeredgewidth(markeredgewidth)
        self._point_size_reduction = 0.5

        self.verticalOffset = None

        # update kwargs before updating data to give the caller a
        # chance to init axes (and hence unit support)
        self.update(kwargs)
        self.pickradius = pickradius
        if is_numlike(self._picker):
            self.pickradius = self._picker

        self._xorig = npy.asarray([])
        self._yorig = npy.asarray([])
        self.set_data(xdata, ydata)

    def contains(self, mouseevent):
        """Test whether the mouse event occurred on the line.  The pick radius determines
        the precision of the location test (usually within five points of the value).  Use
        get/set pickradius() to view or modify it.

        Returns True if any values are within the radius along with {'ind': pointlist},
        npy.where pointlist is the set of points within the radius.

        TODO: sort returned indices by distance
        """
        if callable(self._contains): return self._contains(self,mouseevent)

        if not is_numlike(self.pickradius):
            raise ValueError,"pick radius should be a distance"

        # transform in backend
        if len(self._xy)==0: return False,{}

        xyt = self.get_transform().transform(self._xy)
        xt = xyt[:, 0]
        yt = xyt[:, 1]
        
        if self.figure == None:
            print str(self),' has no figure set'
            pixels = self.pickradius
        else:
            pixels = self.figure.dpi/72. * self.pickradius
            
        if self._linestyle == 'None':
            # If no line, return the nearby point(s)
            d = npy.sqrt((xt-mouseevent.x)**2 + (yt-mouseevent.y)**2)
            ind, = npy.nonzero(npy.less_equal(d, pixels))
        else:
            # If line, return the nearby segment(s)
            ind = segment_hits(mouseevent.x,mouseevent.y,xt,yt,pixels)
        if 0:
            print 'xt', xt, mouseevent.x
            print 'yt', yt, mouseevent.y
            print 'd', (xt-mouseevent.x)**2., (yt-mouseevent.y)**2.
            print d, pixels, ind
        return len(ind)>0,dict(ind=ind)

    def get_pickradius(self):
        'return the pick radius used for containment tests'
        return self.pickradius

    def set_pickradius(self,d):
        """Sets the pick radius used for containment tests

        Accepts: float distance in points.
        """
        self.pickradius = d

    def set_picker(self,p):
        """Sets the event picker details for the line.

        Accepts: float distance in points or callable pick function fn(artist,event)
        """
        if callable(p):
            self._contains = p
        else:
            self.pickradius = p
        self._picker = p

    def get_window_extent(self, renderer):
        bbox = Bbox.unit()
        bbox.update_from_data_xy(self.get_transform().transform(self._xy),
                                 ignore=True)
        # correct for marker size, if any
        if self._marker is not None:
            ms = (self._markersize / 72.0 * self.figure.dpi) * 0.5
            bbox = bbox.padded(ms)
        return bbox

    def set_axes(self, ax):
        Artist.set_axes(self, ax)
        if ax.xaxis is not None:
            self._xcid = ax.xaxis.callbacks.connect('units', self.recache)
        if ax.yaxis is not None:
            self._ycid = ax.yaxis.callbacks.connect('units', self.recache)

    def set_data(self, *args):
        """
        Set the x and y data

        ACCEPTS: (npy.array xdata, npy.array ydata)
        """
        if len(args)==1:
            x, y = args[0]
        else:
            x, y = args

        not_masked = 0
        if not ma.isMaskedArray(x):
            x = npy.asarray(x)
            not_masked += 1
        if not ma.isMaskedArray(y):
            y = npy.asarray(y)
            not_masked += 1
            
        if (not_masked < 2 or
            ((x.shape != self._xorig.shape or npy.any(x != self._xorig)) or
            (y.shape != self._yorig.shape or npy.any(y != self._yorig)))):
            self._xorig = x
            self._yorig = y
            self.recache()
        else:
            self._transformed_path = TransformedPath(self._path, self.get_transform())

    def recache(self):
        #if self.axes is None: print 'recache no axes'
        #else: print 'recache units', self.axes.xaxis.units, self.axes.yaxis.units
        if ma.isMaskedArray(self._xorig) or ma.isMaskedArray(self._yorig):
            x = ma.asarray(self.convert_xunits(self._xorig), float)
            y = ma.asarray(self.convert_yunits(self._yorig), float)
            x = ma.ravel(x)
            y = ma.ravel(y)
        else:
            x = npy.asarray(self.convert_xunits(self._xorig), float)
            y = npy.asarray(self.convert_yunits(self._yorig), float)
            x = npy.ravel(x)
            y = npy.ravel(y)
            
        if len(x)==1 and len(y)>1:
            x = x * npy.ones(y.shape, float)
        if len(y)==1 and len(x)>1:
            y = y * npy.ones(x.shape, float)

        if len(x) != len(y):
            raise RuntimeError('xdata and ydata must be the same length')

        x = x.reshape((len(x), 1))
        y = y.reshape((len(y), 1))

        if ma.isMaskedArray(x) or ma.isMaskedArray(y):
            self._xy = ma.concatenate((x, y), 1)
        else:
            self._xy = npy.concatenate((x, y), 1)
	self._x = self._xy[:, 0] # just a view
	self._y = self._xy[:, 1] # just a view

        # Masked arrays are now handled by the Path class itself
        self._path = Path(self._xy)
        self._transformed_path = TransformedPath(self._path, self.get_transform())


    def set_transform(self, t):
        """
        set the Transformation instance used by this artist

        ACCEPTS: a matplotlib.transforms.Transform instance
        """
        Artist.set_transform(self, t)
        self._transformed_path = TransformedPath(self._path, self.get_transform())
        
    def _is_sorted(self, x):
        "return true if x is sorted"
        if len(x)<2: return 1
        return npy.alltrue(x[1:]-x[0:-1]>=0)

    def draw(self, renderer):
        renderer.open_group('line2d')

        if not self._visible: return
        gc = renderer.new_gc()
        self._set_gc_clip(gc)

        gc.set_foreground(self._color)
        gc.set_antialiased(self._antialiased)
        gc.set_linewidth(self._linewidth)
        gc.set_alpha(self._alpha)
        if self.is_dashed():
            cap = self._dashcapstyle
            join = self._dashjoinstyle
        else:
            cap = self._solidcapstyle
            join = self._solidjoinstyle
        gc.set_joinstyle(join)
        gc.set_capstyle(cap)

        funcname = self._lineStyles.get(self._linestyle, '_draw_nothing')
        if funcname != '_draw_nothing':
            tpath, affine = self._transformed_path.get_transformed_path_and_affine()
            lineFunc = getattr(self, funcname)
            lineFunc(renderer, gc, tpath, affine.frozen())
	    
        if self._marker is not None:
            gc = renderer.new_gc()
            self._set_gc_clip(gc)
            gc.set_foreground(self.get_markeredgecolor())
            gc.set_linewidth(self._markeredgewidth)
            gc.set_alpha(self._alpha)
            funcname = self._markers.get(self._marker, '_draw_nothing')
            if funcname != '_draw_nothing':
                tpath, affine = self._transformed_path.get_transformed_path_and_affine()
                markerFunc = getattr(self, funcname)
                markerFunc(renderer, gc, tpath, affine.frozen())

        renderer.close_group('line2d')

    def get_antialiased(self): return self._antialiased
    def get_color(self): return self._color
    def get_linestyle(self): return self._linestyle

    def get_linewidth(self): return self._linewidth
    def get_marker(self): return self._marker

    def get_markeredgecolor(self):
        if (is_string_like(self._markeredgecolor) and
            self._markeredgecolor == 'auto'):
            if self._marker in self.filled_markers:
                return 'k'
            else:
                return self._color
        else:
            return self._markeredgecolor


        return self._markeredgecolor
    def get_markeredgewidth(self): return self._markeredgewidth

    def get_markerfacecolor(self):
        if (self._markerfacecolor is None or
            (is_string_like(self._markerfacecolor) and
             self._markerfacecolor.lower()=='none') ):
            return self._markerfacecolor
        elif (is_string_like(self._markerfacecolor) and
              self._markerfacecolor.lower() == 'auto'):
            return self._color
        else:
            return self._markerfacecolor


    def get_markersize(self): return self._markersize

    def get_xdata(self, orig=True):
        """
        return the xdata; if orig is true return the original data,
        else the processed data
        """
        if orig:
            return self._xorig
        return self._x

    def get_ydata(self, orig=True):
        """
        return the ydata; if orig is true return the original data,
        else the processed data
        """
        if orig:
            return self._yorig
        return self._y

    def get_xydata(self):
        return self._xy
    
    def set_antialiased(self, b):
        """
        True if line should be drawin with antialiased rendering

        ACCEPTS: [True | False]
        """
        self._antialiased = b

    def set_color(self, color):
        """
        Set the color of the line

        ACCEPTS: any matplotlib color
        """
        self._color = color

    def set_linewidth(self, w):
        """
        Set the line width in points

        ACCEPTS: float value in points
        """
        self._linewidth = w

    def set_linestyle(self, linestyle):
        """
        Set the linestyle of the line

        'steps' is equivalent to 'steps-pre' and is maintained for
        backward-compatibility.
        
        ACCEPTS: [ '-' | '--' | '-.' | ':' | 'steps' | 'steps-pre' | 'steps-mid' | 'steps-post' | 'None' | ' ' | '' ]
        """
        if linestyle not in self._lineStyles:
            verbose.report('Unrecognized line style %s, %s' %
                                            (linestyle, type(linestyle)))
        if linestyle in [' ','']:
            linestyle = 'None'
        self._linestyle = linestyle
        self._lineFunc = self._lineStyles[linestyle]

    def set_marker(self, marker):
        """
        Set the line marker

        ACCEPTS: [ '+' | ',' | '.' | '1' | '2' | '3' | '4'
                 | '<' | '>' | 'D' | 'H' | '^' | '_' | 'd'
                 | 'h' | 'o' | 'p' | 's' | 'v' | 'x' | '|'
                 | TICKUP | TICKDOWN | TICKLEFT | TICKRIGHT
                 | 'None' | ' ' | '' ]

        """
        if marker not in self._markers:
            verbose.report('Unrecognized marker style %s, %s' %
                                            (marker, type(marker)))
        if marker in [' ','']:
            marker = 'None'
        self._marker = marker
        self._markerFunc = self._markers[marker]

    def set_markeredgecolor(self, ec):
        """
        Set the marker edge color

        ACCEPTS: any matplotlib color
        """
        self._markeredgecolor = ec

    def set_markeredgewidth(self, ew):
        """
        Set the marker edge width in points

        ACCEPTS: float value in points
        """
        self._markeredgewidth = ew

    def set_markerfacecolor(self, fc):
        """
        Set the marker face color

        ACCEPTS: any matplotlib color
        """
        self._markerfacecolor = fc

    def set_markersize(self, sz):
        """
        Set the marker size in points

        ACCEPTS: float
        """
        self._markersize = sz

    def set_xdata(self, x):
        """
        Set the data npy.array for x

        ACCEPTS: npy.array
        """
        x = npy.asarray(x)
        self.set_data(x, self._yorig)

    def set_ydata(self, y):
        """
        Set the data npy.array for y

        ACCEPTS: npy.array
        """
        y = npy.asarray(y)
        self.set_data(self._xorig, y)

    def set_dashes(self, seq):
        """
        Set the dash sequence, sequence of dashes with on off ink in
        points.  If seq is empty or if seq = (None, None), the
        linestyle will be set to solid.

        ACCEPTS: sequence of on/off ink in points
        """
        if seq == (None, None) or len(seq)==0:
            self.set_linestyle('-')
        else:
            self.set_linestyle('--')
        self._dashSeq = seq  # TODO: offset ignored for now

    def _draw_nothing(self, *args, **kwargs):
        pass

    
    def _draw_solid(self, renderer, gc, path, trans):
        gc.set_linestyle('solid')
	renderer.draw_path(gc, path, trans)

    
    def _draw_steps_pre(self, renderer, gc, path, trans):
        vertices = self._xy
        steps = ma.zeros((2*len(vertices)-1, 2), npy.float_)

        steps[0::2, 0], steps[1::2, 0] = vertices[:, 0], vertices[:-1, 0]
        steps[0::2, 1], steps[1:-1:2, 1] = vertices[:, 1], vertices[1:, 1]

        path = Path(steps)
        self._draw_solid(renderer, gc, path, trans)


    def _draw_steps_post(self, renderer, gc, path, trans):
        vertices = self._xy
        steps = ma.zeros((2*len(vertices)-1, 2), npy.float_)

        steps[::2, 0], steps[1:-1:2, 0] = vertices[:, 0], vertices[1:, 0]
        steps[0::2, 1], steps[1::2, 1] = vertices[:, 1], vertices[:-1, 1]

        path = Path(steps)
        self._draw_solid(renderer, gc, path, trans)

        
    def _draw_steps_mid(self, renderer, gc, path, trans):
        vertices = self._xy
        steps = ma.zeros((2*len(vertices), 2), npy.float_)

        steps[1:-1:2, 0] = 0.5 * (vertices[:-1, 0] + vertices[1:, 0])
        steps[2::2, 0] = 0.5 * (vertices[:-1, 0] + vertices[1:, 0])
        steps[0, 0] = vertices[0, 0]
        steps[-1, 0] = vertices[-1, 0]
        steps[0::2, 1], steps[1::2, 1] = vertices[:, 1], vertices[:, 1]

        path = Path(steps)
        self._draw_solid(renderer, gc, path, trans)
        

    def _draw_dashed(self, renderer, gc, path, trans):
        gc.set_linestyle('dashed')
        if self._dashSeq is not None:
            gc.set_dashes(0, self._dashSeq)

	renderer.draw_path(gc, path, trans)


    def _draw_dash_dot(self, renderer, gc, path, trans):
        gc.set_linestyle('dashdot')
	renderer.draw_path(gc, path, trans)

	    
    def _draw_dotted(self, renderer, gc, path, trans):
        gc.set_linestyle('dotted')
	renderer.draw_path(gc, path, trans)

	
    def _draw_point(self, renderer, gc, path, path_trans):
        w = renderer.points_to_pixels(self._markersize) * \
	    self._point_size_reduction * 0.5
        rgbFace = self._get_rgb_face()
	transform = Affine2D().scale(w)
	renderer.draw_markers(
	    gc, Path.unit_circle(), transform, path, path_trans,
	    rgbFace)

	
    def _draw_pixel(self, renderer, gc, path, path_trans):
	rgbFace = self._get_rgb_face()
	transform = Affine2D().translate(-0.5, -0.5)
	renderer.draw_markers(gc, Path.unit_rectangle(), transform,
			      path, path_trans, rgbFace)
	
	
    def _draw_circle(self, renderer, gc, path, path_trans):
        w = renderer.points_to_pixels(self._markersize) * 0.5
        rgbFace = self._get_rgb_face()
	transform = Affine2D().scale(w, w)
	renderer.draw_markers(
	    gc, Path.unit_circle(), transform, path, path_trans,
	    rgbFace)


    _triangle_path = Path([[0.0, 1.0], [-1.0, -1.0], [1.0, -1.0], [0.0, 1.0]])
    def _draw_triangle_up(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset, offset)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, self._triangle_path, transform,
			      path, path_trans, rgbFace)


    def _draw_triangle_down(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset, -offset)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, self._triangle_path, transform,
			      path, path_trans, rgbFace)

	
    def _draw_triangle_left(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset, offset).rotate_deg(90)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, self._triangle_path, transform,
			      path, path_trans, rgbFace)


    def _draw_triangle_right(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset, offset).rotate_deg(-90)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, self._triangle_path, transform,
			      path, path_trans, rgbFace)


    def _draw_square(self, renderer, gc, path, path_trans):
        side = renderer.points_to_pixels(self._markersize)
	transform = Affine2D().translate(-0.5, -0.5).scale(side)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_rectangle(), transform,
			      path, path_trans, rgbFace)

	
    def _draw_diamond(self, renderer, gc, path, path_trans):
        side = renderer.points_to_pixels(self._markersize)
	transform = Affine2D().translate(-0.5, -0.5).rotate_deg(45).scale(side)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_rectangle(), transform,
			      path, path_trans, rgbFace)

	
    def _draw_thin_diamond(self, renderer, gc, path, path_trans):
        offset = renderer.points_to_pixels(self._markersize)
	transform = Affine2D().translate(-0.5, -0.5) \
	    .rotate_deg(45).scale(offset * 0.6, offset)
        rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_rectangle(), transform,
			      path, path_trans, rgbFace)

	
    def _draw_pentagon(self, renderer, gc, path, path_trans):
        offset = 0.5 * renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_regular_polygon(5), transform,
			      path, path_trans, rgbFace)

	
    def _draw_hexagon1(self, renderer, gc, path, path_trans):
        offset = 0.5 * renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_regular_polygon(6), transform,
			      path, path_trans, rgbFace)

	
    def _draw_hexagon2(self, renderer, gc, path, path_trans):
        offset = 0.5 * renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(30)
	rgbFace = self._get_rgb_face()
	renderer.draw_markers(gc, Path.unit_regular_polygon(6), transform,
			      path, path_trans, rgbFace)


    _line_marker_path = Path([[0.0, -1.0], [0.0, 1.0]])
    def _draw_vline(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	renderer.draw_markers(gc, self._line_marker_path, transform,
			      path, path_trans)

		
    def _draw_hline(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(90)
	renderer.draw_markers(gc, self._line_marker_path, transform,
			      path, path_trans)

		
    _tickhoriz_path = Path([[0.0, 0.5], [1.0, 0.5]])
    def _draw_tickleft(self, renderer, gc, path, path_trans):
        offset = renderer.points_to_pixels(self._markersize)
	marker_transform = Affine2D().scale(-offset, 1.0)
	renderer.draw_markers(gc, self._tickhoriz_path, marker_transform,
			      path, path_trans)

	
    def _draw_tickright(self, renderer, gc, path, path_trans):
        offset = renderer.points_to_pixels(self._markersize)
	marker_transform = Affine2D().scale(offset, 1.0)
	renderer.draw_markers(gc, self._tickhoriz_path, marker_transform,
			      path, path_trans)

	
    _tickvert_path = Path([[-0.5, 0.0], [-0.5, 1.0]])
    def _draw_tickup(self, renderer, gc, path, path_trans):
        offset = renderer.points_to_pixels(self._markersize)
	marker_transform = Affine2D().scale(1.0, offset)
	renderer.draw_markers(gc, self._tickvert_path, marker_transform,
			      path, path_trans)

	
    def _draw_tickdown(self, renderer, gc, path, path_trans):
        offset = renderer.points_to_pixels(self._markersize)
	marker_transform = Affine2D().scale(1.0, -offset)
	renderer.draw_markers(gc, self._tickvert_path, marker_transform,
			      path, path_trans)


    _plus_path = Path([[-1.0, 0.0], [1.0, 0.0],
		       [0.0, -1.0], [0.0, 1.0]],
		      [Path.MOVETO, Path.LINETO,
		       Path.MOVETO, Path.LINETO])
    def _draw_plus(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	renderer.draw_markers(gc, self._plus_path, transform,
			      path, path_trans)


    _tri_path = Path([[0.0, 0.0], [0.0, -1.0],
		      [0.0, 0.0], [0.8, 0.5],
		      [0.0, 0.0], [-0.8, 0.5]],
		     [Path.MOVETO, Path.LINETO,
		      Path.MOVETO, Path.LINETO,
		      Path.MOVETO, Path.LINETO])
    def _draw_tri_down(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	renderer.draw_markers(gc, self._tri_path, transform,
			      path, path_trans)

	
    def _draw_tri_up(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(180)
	renderer.draw_markers(gc, self._tri_path, transform,
			      path, path_trans)

	
    def _draw_tri_left(self, renderer, gc, path, path_trans):
	offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(90)
	renderer.draw_markers(gc, self._tri_path, transform,
			      path, path_trans)

	
    def _draw_tri_right(self, renderer, gc, path, path_trans):
	offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(270)
	renderer.draw_markers(gc, self._tri_path, transform,
			      path, path_trans)


    _caret_path = Path([[-1.0, 1.5], [0.0, 0.0], [1.0, 1.5]], closed=False)
    def _draw_caretdown(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	renderer.draw_markers(gc, self._caret_path, transform,
			      path, path_trans)

	
    def _draw_caretup(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(180)
	renderer.draw_markers(gc, self._caret_path, transform,
			      path, path_trans)

	
    def _draw_caretleft(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(90)
	renderer.draw_markers(gc, self._caret_path, transform,
			      path, path_trans)

	
    def _draw_caretright(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset).rotate_deg(270)
	renderer.draw_markers(gc, self._caret_path, transform,
			      path, path_trans)


    _x_path = Path([[-1.0, -1.0], [1.0, 1.0],
		    [-1.0, 1.0], [1.0, -1.0]],
		   [Path.MOVETO, Path.LINETO,
		    Path.MOVETO, Path.LINETO])
    def _draw_x(self, renderer, gc, path, path_trans):
        offset = 0.5*renderer.points_to_pixels(self._markersize)
	transform = Affine2D().scale(offset)
	renderer.draw_markers(gc, self._x_path, transform,
			      path, path_trans)

	
    def update_from(self, other):
        'copy properties from other to self'
        Artist.update_from(self, other)
        self._linestyle = other._linestyle
        self._linewidth = other._linewidth
        self._color = other._color
        self._markersize = other._markersize
        self._markerfacecolor = other._markerfacecolor
        self._markeredgecolor = other._markeredgecolor
        self._markeredgewidth = other._markeredgewidth
        self._dashSeq = other._dashSeq
        self._dashcapstyle = other._dashcapstyle
        self._dashjoinstyle = other._dashjoinstyle
        self._solidcapstyle = other._solidcapstyle
        self._solidjoinstyle = other._solidjoinstyle

        self._linestyle = other._linestyle
        self._marker = other._marker


    def _get_rgb_face(self):
        facecolor = self.get_markerfacecolor()
        if is_string_like(facecolor) and facecolor.lower()=='none':
            rgbFace = None
        else:
            rgbFace = colorConverter.to_rgb(facecolor)
        return rgbFace

    # some aliases....
    def set_aa(self, val):
        'alias for set_antialiased'
        self.set_antialiased(val)

    def set_c(self, val):
        'alias for set_color'
        self.set_color(val)


    def set_ls(self, val):
        'alias for set_linestyle'
        self.set_linestyle(val)


    def set_lw(self, val):
        'alias for set_linewidth'
        self.set_linewidth(val)


    def set_mec(self, val):
        'alias for set_markeredgecolor'
        self.set_markeredgecolor(val)


    def set_mew(self, val):
        'alias for set_markeredgewidth'
        self.set_markeredgewidth(val)


    def set_mfc(self, val):
        'alias for set_markerfacecolor'
        self.set_markerfacecolor(val)


    def set_ms(self, val):
        'alias for set_markersize'
        self.set_markersize(val)

    def get_aa(self):
        'alias for get_antialiased'
        return self.get_antialiased()

    def get_c(self):
        'alias for get_color'
        return self.get_color()


    def get_ls(self):
        'alias for get_linestyle'
        return self.get_linestyle()


    def get_lw(self):
        'alias for get_linewidth'
        return self.get_linewidth()


    def get_mec(self):
        'alias for get_markeredgecolor'
        return self.get_markeredgecolor()


    def get_mew(self):
        'alias for get_markeredgewidth'
        return self.get_markeredgewidth()


    def get_mfc(self):
        'alias for get_markerfacecolor'
        return self.get_markerfacecolor()


    def get_ms(self):
        'alias for get_markersize'
        return self.get_markersize()

    def set_dash_joinstyle(self, s):
        """
        Set the join style for dashed linestyles
        ACCEPTS: ['miter' | 'round' | 'bevel']
        """
        s = s.lower()
        if s not in self.validJoin:
            raise ValueError('set_dash_joinstyle passed "%s";\n' % (s,)
                  + 'valid joinstyles are %s' % (self.validJoin,))
        self._dashjoinstyle = s

    def set_solid_joinstyle(self, s):
        """
        Set the join style for solid linestyles
        ACCEPTS: ['miter' | 'round' | 'bevel']
        """
        s = s.lower()
        if s not in self.validJoin:
            raise ValueError('set_solid_joinstyle passed "%s";\n' % (s,)
                  + 'valid joinstyles are %s' % (self.validJoin,))
        self._solidjoinstyle = s


    def get_dash_joinstyle(self):
        """
        Get the join style for dashed linestyles
        """
        return self._dashjoinstyle

    def get_solid_joinstyle(self):
        """
        Get the join style for solid linestyles
        """
        return self._solidjoinstyle

    def set_dash_capstyle(self, s):
        """
        Set the cap style for dashed linestyles
        ACCEPTS: ['butt' | 'round' | 'projecting']
        """
        s = s.lower()
        if s not in self.validCap:
            raise ValueError('set_dash_capstyle passed "%s";\n' % (s,)
                  + 'valid capstyles are %s' % (self.validCap,))

        self._dashcapstyle = s


    def set_solid_capstyle(self, s):
        """
        Set the cap style for solid linestyles
        ACCEPTS: ['butt' | 'round' |  'projecting']
        """
        s = s.lower()
        if s not in self.validCap:
            raise ValueError('set_solid_capstyle passed "%s";\n' % (s,)
                  + 'valid capstyles are %s' % (self.validCap,))

        self._solidcapstyle = s


    def get_dash_capstyle(self):
        """
        Get the cap style for dashed linestyles
        """
        return self._dashcapstyle

    
    def get_solid_capstyle(self):
        """
        Get the cap style for solid linestyles
        """
        return self._solidcapstyle

    
    def is_dashed(self):
        'return True if line is dashstyle'
        return self._linestyle in ('--', '-.', ':')


lineStyles = Line2D._lineStyles
lineMarkers = Line2D._markers

artist.kwdocd['Line2D'] = artist.kwdoc(Line2D)
