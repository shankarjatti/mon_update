# gr-dsd port to GNU Radio 3.8 (SWIG) — for the terrestrial decoders on CH2

Goal (user: EVERYTHING in UHD 3.15 + GNU Radio 3.8): run the DMR/P25/NXDN/D-STAR
decode (DSD) and TETRA under GR 3.8, fed by our monitoring CH2 feed. The repo
(github shankarjatti/1stversiondone) targets GR 3.10 (pybind) + UHD 4 + B210.

## Findings (2026-10-12)
- gr-dsd / gr-dsd-ext are pybind (GR>=3.9) -> cannot run on GR 3.8 (SWIG). Must port.
- The repo uses gr-dsd-EXT (extra fields: last_talkgroup/last_source/nac). Port the ext.
- Engine is bundled: mbelib/ (C) + dsd/ (C, project 'dsd') — version-independent.
  Deps: IT++ (libitpp-dev INSTALLED), libsndfile (INSTALLED).
- GR wrapper = lib/dsd_block_ff_impl.cc/.h (~320 lines), public include/dsd/dsd_block_ff.h.
  GR3.9->3.8 changes: std::shared_ptr -> boost::shared_ptr; gnuradio::make_block_sptr
  -> gnuradio::get_initial_sptr(new ...). work() signature same. base gr::sync_decimator OK.
- TETRA block = pure Python gr.basic_block (deps/gr_tetra_decoder/tetra_decoder_block.py)
  + libtetrakit_capi.so (native x86-64, ctypes). Easy: fix hardcoded sys.path, use in 3.8.
- Toolchain OK: gr_modtool(3.8), swig 4.0.2, GrSwig.cmake. Template: ~/REPO/gr-doa (our 3.8 SWIG OOT).

## Plan
1. gr_modtool newmod dsd  -> gr-dsd (3.8 skeleton, module name 'dsd' so `import dsd` works).
2. Add engine subdirs (mbelib, dsd) + wire CMake; keep C sources as-is.
3. Add wrapper: include/dsd/dsd_block_ff.h (+api.h), lib/dsd_block_ff_impl.{h,cc} with
   boost::shared_ptr + get_initial_sptr. Keep the ext getters (last_talkgroup/source/nac).
4. swig/dsd_swig.i (mirror doa_swig.i) exposing dsd_block_ff + the enums.
5. grc/dsd_dsd_block_ff.block.yml (already 3.8 YAML).
6. cmake: find_package(Gnuradio 3.8); include(GrSwig),(GrPython); link IT++, sndfile, mbe, dsd.
7. build + make install into ~/gnuradio-3.8 ; verify `import dsd` under GR 3.8 env.
8. Then: demod chain + flowgraph in GRC 3.8, fed by ZeroMQ SUB from mon_scan CH2 (port 5202),
   resampled to the DSD input rate. TETRA likewise.

## Work dirs
- ~/radar2/terrestrial_src        (clone of the repo)
- ~/radar2/gr-dsd-ext-38          (copy of gr-dsd-ext, reference)
- ~/radar2/gr-dsd (new)           (the 3.8 SWIG port, built here)

## STATUS 2026-10-12 — DSD PORT DONE
- gr-dsd built + installed for GR 3.8 (SWIG) at ~/radar2/gr-dsd, installed into ~/gnuradio-3.8.
- Changes made vs the 3.10 ext source:
  * include/dsd/dsd_block_ff.h: sptr std::shared_ptr -> boost::shared_ptr (+<boost/shared_ptr.hpp>).
  * lib/dsd_block_ff_impl.cc: make_block_sptr -> gnuradio::get_initial_sptr(new ...).
  * top CMakeLists: find_package(Gnuradio 3.8); add_subdirectory(mbelib),(dsd) before lib.
  * lib/CMakeLists: target_link_libraries(gnuradio-dsd PUBLIC ...-runtime PRIVATE dsd).
  * swig/dsd_swig.i: gr_modtool-generated (GR_SWIG_BLOCK_MAGIC2) - works as-is.
  * engine (mbelib/, dsd/) copied unchanged (C); deps IT++ + libsndfile (system).
- VERIFIED under GR 3.8: import dsd OK (from ~/gnuradio-3.8, not the 3.10 leak);
  dsd.dsd_block_ff(frame,mod,uv,eb,verb) makes the block; ext getters work;
  tiny flowgraph null->dsd->null runs; engine prints "Decoding only DMR/MOTOTRBO frames".
  Usage: dsd.dsd_block_ff(dsd.dsd_FRAME_*, dsd.dsd_MOD_*, uvquality, errorbars, verbosity).
- NEXT: (a) TETRA block (python gr.basic_block + libtetrakit_capi.so) -> GR 3.8: fix
  hardcoded sys.path, test import/instantiate. (b) demod chains + GRC 3.8 flowgraph fed
  by a ZeroMQ SUB from mon_scan CH2 (5202), resampled to the DSD/TETRA input rate.

## STATUS 2026-10-12 — TETRA C++ OOT DONE
- gr-tetra (GR 3.8 SWIG C++ OOT) at ~/radar2/gr-tetra, installed into ~/gnuradio-3.8.
- gr::block: in 1xbyte (channel bits) -> rxSymbol; out 4xfloat (TN1-4 PCM); msg port call_log.
- Links prebuilt libtetrakit_capi.so + libtetra_codec.so (copied to lib/prebuilt, installed
  to ~/gnuradio-3.8/lib, INSTALL_RPATH set). zlib + pthread. nlohmann/json vendored
  (include/tetra/vendor/nlohmann) from the sdrangel snap.
- rx thread: UDP 42100 JSON reports -> UPLANE/TCH_S: base64+zlib -> ACELP codec -> queue per TN;
  else -> call_log PMT dict (all JSON fields). general_work feeds bits + drains audio (carry).
- VERIFIED under GR 3.8: import tetra; tetra.tetra_decoder_block(1,True,False,False); flowgraph
  byte->tetra->4 null sinks runs; rx thread + codec + capi linked. grc block.yml installed.

## BOTH DECODERS NOW IN GR 3.8 / UHD 3.15
- dsd  : DMR / P25 / NXDN / D-STAR  (gr-dsd)   -> import dsd;   dsd.dsd_block_ff(...)
- tetra: TETRA                       (gr-tetra) -> import tetra; tetra.tetra_decoder_block(...)
- NEXT: per-protocol demod chains + a GRC/py flowgraph fed by a ZeroMQ SUB from mon_scan CH2
  (port 5202), resampled to each decoder's input rate. Then run on-hardware with DMR radio.

## STATUS 2026-10-12 — DSD DECODE VERIFIED ON REAL SIGNAL + CH2 decode flowgraph
- Fed dstar_48k.wav (real D-STAR discriminator) into dsd.dsd_block_ff(DSTAR,GFSK):
  synced, decoded headers (WB7DZG/KB7WUK/CQCQCQ), real audio out (rms 5064). WORKS.
- terrestrial38/: zmq_cc_source.py (SUB to mon_scan CH2 feed) + decode_dsd.py
  (zmq->xlating 2e6->50k->quad demod->resample 48/50->dsd->wav+talkgroup). Builds+runs.
- NEXT: TETRA demod chain (pi4dqpsk) + live test (USRP + DMR radio + CH2 tuned).
