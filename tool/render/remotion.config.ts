import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setStillImageFormat("png");
// Remotion writes every frame as a JPEG into a temp folder, so concurrency
// multiplies peak scratch space AND memory. 2 is slower per clip but survives a
// long batch on an 8 GB Mac with little free disk. render_clip.py passes
// CLIP_TOOL_REMOTION_CONCURRENCY on the command line, which overrides this.
Config.setConcurrency(2);
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
Config.setAudioBitrate("192k");
Config.setJpegQuality(90);
