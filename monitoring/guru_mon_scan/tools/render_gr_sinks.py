# Render GNU Radio 3.8 QT GUI sinks off-screen (GRC default settings) to PNG, as the style reference.
import sys, time, os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5 import Qt
import sip
from gnuradio import gr, blocks, analog, qtgui
from gnuradio.filter import firdes
OUT = sys.argv[1]
app = Qt.QApplication(["gr"])
fs = 1e6
tb = gr.top_block()
noise = analog.noise_source_c(analog.GR_GAUSSIAN, 0.05, 0)
tone = analog.sig_source_c(fs, analog.GR_COS_WAVE, 60e3, 0.3, 0)
add = blocks.add_vcc(1)
thr = blocks.throttle(gr.sizeof_gr_complex, fs, True)
# GRC defaults of each sink
f = qtgui.freq_sink_c(1024, firdes.WIN_BLACKMAN_hARRIS, 2442e6, fs, "", 1)
f.set_update_time(0.10); f.set_y_axis(-140, 10); f.set_y_label('Relative Gain', 'dB'); f.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, ""); f.enable_autoscale(False); f.enable_grid(False); f.set_fft_average(1.0); f.enable_axis_labels(True); f.enable_control_panel(False)
t = qtgui.time_sink_c(1024, fs, "", 1)
t.set_update_time(0.10); t.set_y_axis(-1, 1); t.set_y_label('Amplitude', ""); t.enable_tags(True); t.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, 0, ""); t.enable_autoscale(False); t.enable_grid(False); t.enable_axis_labels(True); t.enable_control_panel(False); t.enable_stem_plot(False)
w = qtgui.waterfall_sink_c(1024, firdes.WIN_BLACKMAN_hARRIS, 2442e6, fs, "", 1)
w.set_update_time(0.10); w.enable_grid(False); w.enable_axis_labels(True); w.set_intensity_range(-140, 10)
c = qtgui.const_sink_c(1024, "", 1)
c.set_update_time(0.10); c.set_y_axis(-2, 2); c.set_x_axis(-2, 2); c.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, ""); c.enable_autoscale(False); c.enable_grid(False); c.enable_axis_labels(True)
tb.connect(noise, (add, 0)); tb.connect(tone, (add, 1)); tb.connect(add, thr)
for s in (f, t, w, c): tb.connect(thr, s)
wids = {}
for name, s in (("freq", f), ("time", t), ("waterfall", w), ("const", c)):
    q = sip.wrapinstance(s.pyqwidget(), Qt.QWidget); q.resize(820, 420); q.show(); wids[name] = q
# second set: grid + control panel ON (what the GUI looks like with its options)
f2 = qtgui.freq_sink_c(1024, firdes.WIN_BLACKMAN_hARRIS, 2442e6, fs, "", 1); f2.enable_grid(True); f2.enable_control_panel(True); f2.set_y_axis(-140, 10)
t2 = qtgui.time_sink_c(1024, fs, "", 1); t2.enable_grid(True); t2.enable_control_panel(True); t2.set_y_axis(-1, 1)
for s in (f2, t2): tb.connect(thr, s)
for name, s in (("freq_grid_panel", f2), ("time_grid_panel", t2)):
    q = sip.wrapinstance(s.pyqwidget(), Qt.QWidget); q.resize(980, 460); q.show(); wids[name] = q
tb.start()
t0 = time.time()
while time.time() - t0 < 4.0:
    app.processEvents(); time.sleep(0.02)
for name, q in wids.items():
    app.processEvents(); q.grab().save(os.path.join(OUT, name + ".png"))
tb.stop(); tb.wait()
print("saved", sorted(os.listdir(OUT)))
