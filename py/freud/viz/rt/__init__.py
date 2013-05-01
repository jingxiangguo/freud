from __future__ import division, print_function

import numpy
import math
import time
from ctypes import c_void_p
import logging
logger = logging.getLogger(__name__);

# pyside and OpenGL are required deps for this module (not for all of freud), but we don't want to burden user scripts
# with lots of additional imports. So try and import them and throw a warning up to the parent module to handle
try:
    import OpenGL
    from PySide import QtCore, QtGui, QtOpenGL
except ImportError:
    logger.warning('Either PySide or pyopengl is not available, aborting rt initialization');
    raise ImportWarning('PySide or pyopengl not available');

# set opengl options
OpenGL.FORWARD_COMPATIBLE_ONLY = True
OpenGL.ERROR_ON_COPY = True
OpenGL.INFO_LOGGING = False
OpenGL.ERROR_CHECKING = False

# force gl logger to emit only warnings and above
gl_logger = logging.getLogger('OpenGL')
gl_logger.setLevel(logging.WARNING)

from OpenGL import GL as gl

from freud import qt;
from . import rastergl

## \package freud.viz.rt
#
# Real-time visualization Qt widgets and rendering routines. freud.qt.init_app() must be called prior to constructing 
# any class in rt.
#
# \note freud.viz.rt **requires** pyside and pyopengl. If these dependencies are not present, a warning is issued to the
# logger, but execution continues with freud.viz.rt = None.
#

null = c_void_p(0)

## Widget for rendering scenes in real-time
#
# GLWidget renders a Scene in real-time using OpenGL. It is a low-level widget that can be embedded in other windows.
# MainWindow embeds a central GLWidget around a feature-providing interface.
# 
# It (currently) only offers 2D camera control. Updates to the
# camera are made directly in the reference scene, so code external to GLWidget that uses the same scene will render
# the same point of view.
#
# ### Controls:
# - Panning mode (indicated by an open hand mouse cursor)
#     - *Click and drag* to **translate** the camera's x,y coordinates
# - At any time
#     - *Turn the mouse wheel* to **zoom** (*hold ctrl* to make finer adjustments)
#
# \note On mac
# - *ctrl* is *command*
# - *meta* is *control*
#
# TODO: Add 3d in as an option, or a 2nd widget?
# TODO: What about scenes that have both 2d and 3d geometry?
#
class GLWidget(QtOpenGL.QGLWidget):
    # animation states the UI code can take
    ANIM_IDLE = 1;
    ANIM_PAN = 2;
    
    ## Create a GLWidget
    # \param scene the Scene to render
    # \param *args non-keyword args passed on to QGLWidget 
    # \param **kwargs keyword args passed on to QGLWidget 
    #
    def __init__(self, scene, *args, **kwargs):
        if not qt.is_initialized():
            raise RuntimeError('freud.qt.init_app() must be called before constructing a GLWidget');
        
        QtOpenGL.QGLWidget.__init__(self, *args, **kwargs)
        self.scene = scene;
        
        self.setCursor(QtCore.Qt.OpenHandCursor)
        
        # initialize state machine variables
        self._anim_state = GLWidget.ANIM_IDLE;
        self._prev_pos = numpy.array([0,0], dtype=numpy.float32);
        self._prev_time = time.time();
        self._pan_vel = numpy.array([0,0], dtype=numpy.float32);
        self._initial_pan_vel = numpy.array([0,0], dtype=numpy.float32);
        self._initial_pan_time = time.time();
        
        # timer for the animation loop
        self._timer_animate = QtCore.QTimer(self)
        self._timer_animate.timeout.connect(self.animate)
        self._timer_animate.start();
        
        self.setFocusPolicy(QtCore.Qt.ClickFocus);
    
    ## \internal 
    # \brief Resize the GL viewport
    #
    # Set the gl viewport size and update the camera resolution
    #
    def resizeGL(self, w, h):
        gl.glViewport(0, 0, w, h)
        self.scene.camera.setAspect(w/h);
        self.scene.camera.resolution = h;
    
    ## \internal
    # \brief Paint the GL scene
    #
    # Clear the draw buffers and redraws the scene
    #
    def paintGL(self):
        gl.glClearColor(1.0, 1.0, 1.0, 0.0);
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT);
        self.draw_gl.startFrame();
        self.draw_gl.draw(self.scene);
        self.draw_gl.endFrame();

    ## \internal
    # \brief Initialize the OpenGL renderer
    #
    # Initializes OpenGL and prints information about it to logger.info.
    #
    def initializeGL(self):
        logger.info('OpenGL version: ' + gl.glGetString(gl.GL_VERSION))
        self.draw_gl = rastergl.DrawGL();

    ## \internal
    # \brief Animation slot
    #
    # Called at idle while animating. Currently, only panning is animated. If self._anim_state is ANIM_PAN
    # then the camera is panned for ~1 second after the animation starts. The camera velocity is decreased
    # on an exponential curve.
    #
    # To start the animation loop, mouseReleaseEvent sets the initial velocity, initial time, previous time,
    # and sets the animation state to ANIM_PAN. The timer _timer_animate calls animate() on idle.
    #
    # Once the velocity reaches zero, _anim_state is set back to ANIM_IDLE.
    #
    def animate(self):
        # If we are idle, stop the timer
        if self._anim_state == GLWidget.ANIM_IDLE:
            self._timer_animate.stop();
        
        # If we are panning
        elif self._anim_state == GLWidget.ANIM_PAN:
            # Decrease the pan velocity on an exponential curve
            cur_time = time.time();
            self._pan_vel = numpy.exp(-(cur_time - self._initial_pan_time)/0.1) * self._initial_pan_vel;
            
            # Compute a delta (in camera units) and move the camera
            delta = self._pan_vel * (cur_time - self._prev_time) * self.scene.camera.pixel_size;
            delta[0] = delta[0] * -1;
            self.scene.camera.position[0:2] += delta;
            self._prev_time = cur_time;
            
            # Go back to the idle state when we come to a stop
            if numpy.dot(self._pan_vel, self._pan_vel) < 100:
                self._anim_state = GLWidget.ANIM_IDLE;
            
            # Redraw the GL view
            self.updateGL();

    ## \internal
    # \brief Close event
    #
    # Releases OpenGL resources when the widget is closed. 
    #
    def closeEvent(self, event):
        # stop the animation loop
        self._anim_state = GLWidget.ANIM_IDLE;
        self._timer_animate.stop();
        
        # make the gl context current and free resources
        self.makeCurrent();
        self.draw_gl.destroy();

    ## \internal
    # \brief Handle mouse move (while dragging) event
    #
    # Update the camera position based on the movement from the previous position while dragging with the left mouse
    # button.
    #
    def mouseMoveEvent(self, event):

        if event.buttons() & QtCore.Qt.LeftButton:
            # update camera position
            cur_time = time.time();
            cur_pos = numpy.array([event.x(), event.y()], dtype=numpy.float32);
            delta = (cur_pos - self._prev_pos) * self.scene.camera.pixel_size;
            delta[0] = delta[0] * -1;
            self.scene.camera.position[0:2] += delta;
            
            # compute pan velocity in camera pixels/second
            self._pan_vel[:] = (cur_pos - self._prev_pos) / (cur_time - self._prev_time);
            
            self._prev_time = cur_time;
            self._prev_pos = cur_pos;
            
            # Redraw the GL view
            self.updateGL();
            
            event.accept();
        else:
            event.ignore();

    ## \internal
    # \brief Handle mouse press event
    #
    # Start mouse-control panning the camera when the left button is pressed.
    #
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # stop any running pan animations
            self._anim_state = GLWidget.ANIM_IDLE;
            
            # save the drag start position, time, and update the cursor
            self._prev_pos[0] = event.x();
            self._prev_pos[1] = event.y();
            self._prev_time = time.time();
            self._pan_vel[:] = 0;
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept();
        else:
            event.ignore();

    ## \internal
    # \brief Handle mouse release event
    #
    # stop mouse-control panning the camera when the left button is released
    # and start the animated panning
    #
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # switch to the panning animation, set the initial pan vel and time, and update the cursor
            self._anim_state = GLWidget.ANIM_PAN;
            self._timer_animate.start();
            self._initial_pan_vel[:] = self._pan_vel[:];
            self._initial_pan_time = self._prev_time;
            self.setCursor(QtCore.Qt.OpenHandCursor)
            event.accept();
        else:
            event.ignore();
    
    ## \internal
    # \brief Zoom in response to a mouse wheel event
    #
    def wheelEvent(self, event):
        # control speed based on modifiers (ctrl/cmd = slow)
        if event.modifiers() == QtCore.Qt.ControlModifier:
            speed = 0.05;
        else:
            speed = 0.2;
        
        if event.orientation() == QtCore.Qt.Vertical:
            # zoom the camera based on the mouse wheel. Zooming is a constant factor reduction (or increase) in size.
            f = 1 - speed * float(event.delta())/120;
            self.scene.camera.setHeight(self.scene.camera.getHeight() * f);
            
            # Redraw the GL view
            self.updateGL();
            event.accept();

    ## return a default size
    def sizeHint(self):
        return QtCore.QSize(1200,1200);

## Delayed scene update manager
#
# Setting frames in scenes may take a while when there is a lot of processing to do. This processing should not be done
# in the main thread so the GUI remains responsive. The SceneUpdateManager updates the scene frame in the background.
# It is designed to be assigned to a QThread.
#
# **Implementation details**
# SceneUpdateManager starts a QTimer for idle processing. It tracks a single frame to update. When a new frame is
# requested, it overrides the old one there. When the idle processing timer triggers, the scene is updated to the
# currently requested frame and then the timer is stopped.
#
# The update manager has a signal which it emits when the frame is updated. TODO: somehow we need to make the
# scene frame update atomic.... otherwise partially updated frames might be rendered. Not sure if a mutex is the right
# solution, since that would just lock up the GUI if it attempts to draw the scene.....
#
class SceneUpdateManager(QtCore.QObject):
    completed = QtCore.Signal();
    
    def __init__(self, scene):
        QtCore.QObject.__init__(self);
        self.scene = scene;

    @QtCore.Slot()
    def initialize(self):
        self._target_frame = None;        
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.process)

    @QtCore.Slot()
    def process(self):
        if self._target_frame is None:
            self._timer.stop();
        else:
            self.scene.setFrame(self._target_frame);
            self._target_frame = None;
            self.completed.emit();
    
    @QtCore.Slot()
    def loadFrame(self, target_frame):
        self._target_frame = target_frame;
        self._timer.start();

## Main window for freud viz
#
# MainWindow hosts a central GLWidget display with feature-providing menus, dock-able control panels, etc...
#
class MainWindow(QtGui.QMainWindow):
    frame_change = QtCore.Signal(int);
    
    def __init__(self, scene, immediate=False, *args, **kwargs):
        QtGui.QMainWindow.__init__(self, *args, **kwargs)

        self.scene = scene;
        self._frame = -1;
        self._immediate = immediate;
        
        # initialize the gl display
        self.glWidget = GLWidget(scene)
        self.setCentralWidget(self.glWidget)
        self.setWindowTitle('freud.viz')

        self.timer_animate = QtCore.QTimer(self)
        self.timer_animate.timeout.connect(self.gotoNextFrame)

        self.statusBar().showMessage('Ready');
        
        # initialize the scene update manager
        if not self._immediate:
            self.update_manager = SceneUpdateManager(scene);
            self.update_thread = QtCore.QThread();
            self.update_manager.moveToThread(self.update_thread);
            self.update_thread.started.connect(self.update_manager.initialize);
            self.update_manager.completed.connect(self.update);
            self.frame_change.connect(self.update_manager.loadFrame);
            self.update_thread.start();
        
        self.createActions();
        self.createToolbars();
        self.createSubWidgets();
        self.createMenus();
        self.restoreSettings();
    
    ## Create the actions
    def createActions(self):
        self.action_close = QtGui.QAction('&Close', self);
        self.action_close.setShortcut('Ctrl+W');
        self.action_close.setStatusTip('Close window');
        self.action_close.triggered.connect(self.close);
    
        self.action_play = QtGui.QAction('&Play', self);
        self.action_play.setShortcut('Space');
        self.action_play.setStatusTip('Play or pause the animation');
        self.action_play.setCheckable(True);
        self.action_play.triggered[bool].connect(self.play);

        self.action_next = QtGui.QAction('&Next frame', self);
        self.action_next.setShortcut('Right');
        self.action_next.setStatusTip('Advance the animation to the next frame');
        self.action_next.triggered.connect(self.gotoNextFrame);

        self.action_prev = QtGui.QAction('Pre&v frame', self);
        self.action_prev.setShortcut('Left');
        self.action_prev.setStatusTip('Go to the previous animation frame');
        self.action_prev.triggered.connect(self.gotoPrevFrame);
        
        self.action_first = QtGui.QAction('&First frame', self);
        self.action_first.setShortcut('Home');
        self.action_first.setStatusTip('Go to the first animation frame');
        self.action_first.triggered.connect(self.gotoFirstFrame);

        self.action_last = QtGui.QAction('&Last frame', self);
        self.action_last.setShortcut('End');
        self.action_last.setStatusTip('Go to the last animation frame');
        self.action_last.triggered.connect(self.gotoLastFrame);

    ## Create the main window menus
    def createMenus(self):
        viz_menu = self.menuBar().addMenu('&Viz')
        viz_menu.addAction(self.action_close);
        
        popup = self.createPopupMenu();
        popup.setTitle('View');
        view_menu = self.menuBar().addMenu(popup);
        
        animate_menu = self.menuBar().addMenu('&Animate');
        animate_menu.addAction(self.action_play);
        animate_menu.addAction(self.action_prev);
        animate_menu.addAction(self.action_next);
        animate_menu.addAction(self.action_first);
        animate_menu.addAction(self.action_last);
        
    ## Create sub widgets
    def createSubWidgets(self):
        #self.anim_control = AnimationControl();
        
        #self.anim_control_dock = QtGui.QDockWidget("Animation", self)
        #self.anim_control_dock.setAllowedAreas(QtCore.Qt.TopDockWidgetArea | QtCore.Qt.BottomDockWidgetArea)
        #self.anim_control_dock.setWidget(self.anim_control)
        #self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.anim_control_dock)
        pass;
    
    ## Create tool bars
    def createToolbars(self):
        # initialize the non tool button interface elements
        self.frame_slider = QtGui.QSlider(QtCore.Qt.Horizontal, self);
        self.frame_slider.valueChanged[int].connect(self.gotoFrame);
        self.frame_slider.setTickPosition(QtGui.QSlider.TicksBelow);
        self.frame_slider.setTickInterval(10);
        self.frame_slider.setStatusTip('Select frame');
        self.frame_slider.setFocusPolicy(QtCore.Qt.NoFocus);
        self.frame_slider.setMaximum(self.scene.getNumFrames()-1);
        
        self.frame_spinbox = QtGui.QSpinBox(self);
        self.frame_spinbox.setStatusTip('Select frame');
        self.frame_spinbox.valueChanged[int].connect(self.gotoFrame)
        self.frame_spinbox.setWrapping(True);
        self.frame_spinbox.setSuffix(' / '+str(self.scene.getNumFrames()));
        self.frame_spinbox.setMaximum(self.scene.getNumFrames()-1);
        
        self.fps_spinbox = QtGui.QSpinBox(self);
        self.fps_spinbox.setRange(0,60);
        self.fps_spinbox.setStatusTip('Set maximum animation FPS (0 => unlimited)');
        self.fps_spinbox.valueChanged[int].connect(self.setFPS)
        
        self.animation_control_toolbar = QtGui.QToolBar('Animation', self);
        self.animation_control_toolbar.setObjectName('animation_control_toolbar');
        self.animation_control_toolbar.addAction(self.action_play);
        self.animation_control_toolbar.addWidget(self.frame_slider);
        self.animation_control_toolbar.addWidget(self.frame_spinbox);
        self.animation_control_toolbar.addSeparator();
        self.animation_control_toolbar.addWidget(QtGui.QLabel(text='FPS:', parent=self));
        self.animation_control_toolbar.addWidget(self.fps_spinbox);
        self.animation_control_toolbar.setAllowedAreas(QtCore.Qt.TopToolBarArea | QtCore.Qt.BottomToolBarArea);
        
        self.addToolBar(self.animation_control_toolbar);
    
    ## restore saved settings
    def restoreSettings(self):
        settings = QtCore.QSettings("umich.edu", "freud.viz");
        fps = settings.value('rt-MainWindow/fps');
        if fps is not None:
            self.setFPS(fps);
            
        geom = settings.value("rt-MainWindow/geometry");
        if geom is not None:
            self.restoreGeometry(geom);
        
        state = settings.value("rt-MainWindow/window_state");
        if state is not None:
            self.restoreState(state);

    ## Save settings on close
    def closeEvent(self, event):
        self.timer_animate.stop();
        if not self._immediate:
            self.update_thread.quit();
        
        settings = QtCore.QSettings("umich.edu", "freud.viz");
        settings.setValue("rt-MainWindow/geometry", self.saveGeometry());
        settings.setValue("rt-MainWindow/fps", self.fps_spinbox.value());
        settings.setValue("rt-MainWindow/window_state", self.saveState());
        QtGui.QMainWindow.closeEvent(self, event);

    ## Set the animation frame
    @QtCore.Slot(int)
    def gotoFrame(self, frame):
        # two separate controls call this, which means it often gets double updates
        # check a stored frame counter here to see if we already set this frame
        if frame == self._frame:
            return;
        self._frame = frame;
        
        # sync the two separate controls together
        self.frame_slider.setValue(frame);
        self.frame_spinbox.setValue(frame);
        
        # update to the target frame
        if self._immediate:
            self.scene.setFrame(frame);
            self.glWidget.updateGL();
        
        self.frame_change.emit(frame);
    
    ## Set the maximum FPS
    @QtCore.Slot(int)
    def setFPS(self, fps):
        self.fps_spinbox.setValue(fps);
        
        if fps == 0:
            self.timer_animate.setInterval(0);
        else:
            self.timer_animate.setInterval(1000/fps);
    
    ## Play/pause the animation
    @QtCore.Slot()
    def play(self, play=True):
        if play:
            self.timer_animate.start();
        else:
            self.timer_animate.stop();
    
    ## Advance to the next frame
    @QtCore.Slot()
    def gotoNextFrame(self):
        self.frame_spinbox.stepUp();
    
    ## Go back one frame
    @QtCore.Slot()
    def gotoPrevFrame(self):
        self.frame_spinbox.stepDown();
    
    ## Go to start frame
    @QtCore.Slot()
    def gotoFirstFrame(self):
        self.frame_slider.setValue(0);
    
    ## Go to last frame
    @QtCore.Slot()
    def gotoLastFrame(self):
        self.frame_slider.setValue(self.frame_slider.maximum());
    
##########################################
# Module init

# set the default GL format
glFormat = QtOpenGL.QGLFormat();
glFormat.setVersion(2, 1);
glFormat.setProfile( QtOpenGL.QGLFormat.CompatibilityProfile );
glFormat.setSampleBuffers(True);
glFormat.setSwapInterval(0);
QtOpenGL.QGLFormat.setDefaultFormat(glFormat);
