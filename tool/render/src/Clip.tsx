import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
// Inter is bundled from the @fontsource/inter package (SIL Open Font Licence),
// so rendering needs no internet connection once `npm install` has run.
// Only the two weights the composition uses are pulled in.
import "@fontsource/inter/latin-700.css";
import "@fontsource/inter/latin-800.css";

const fontStack =
  "Inter, -apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif";

// Hold the first frame until both weights are ready, so no frame is drawn in
// the fallback font. If loading fails the render carries on with the fallback.
if (typeof document !== "undefined" && document.fonts) {
  const handle = delayRender("Loading Inter");
  Promise.all([
    document.fonts.load("700 56px Inter"),
    document.fonts.load("800 46px Inter"),
  ])
    .then(() => continueRender(handle))
    .catch(() => continueRender(handle));
}

export const FPS = 30;

// Music underbed envelope (seconds)
const FADE_IN = 0.6;
const FADE_OUT = 1.5;

// Caption phrase grouping
const MAX_WORDS_PER_PHRASE = 4;

// Hold a phrase on screen through short gaps between words so captions don't
// strobe off between phrases. Longer silences still clear the caption.
const CAPTION_HOLD_S = 1.0;

export type Word = {
  w: string;
  start: number;
  end: number;
};

export type ClipProps = {
  videoSrc: string;
  headline: string;
  words: Word[];
  musicSrc: string | null;
  musicVolume: number;
  orientation: "portrait" | "landscape";
  durationSec: number;
  videoAspect: number;
  bgBlurFill?: boolean;
  // Seconds the headline stays on screen. 0 keeps it up for the whole clip.
  headlineDurationSec?: number;
  hideCaptions?: boolean;
  // "pill" draws dark text in a white rounded box (reads well on busy footage).
  headlineStyle?: "default" | "pill";
  // Solid black band across the top, to cover a headline already baked into the source.
  maskTop?: boolean;
};

type Phrase = { text: string; start: number; end: number };

/**
 * Group words into 3-4 word caption phrases, breaking early on
 * sentence-terminal punctuation so a phrase never straddles a full stop.
 */
const buildPhrases = (words: Word[]): Phrase[] => {
  const phrases: Phrase[] = [];
  let current: Word[] = [];

  const flush = () => {
    if (current.length === 0) return;
    phrases.push({
      text: current
        .map((w) => w.w)
        .join(" ")
        .trim(),
      start: current[0].start,
      end: current[current.length - 1].end,
    });
    current = [];
  };

  for (const word of words) {
    if (!word.w || !word.w.trim()) continue;
    current.push(word);
    const terminal = /[.!?]$/.test(word.w.trim());
    if (terminal || current.length >= MAX_WORDS_PER_PHRASE) {
      flush();
    }
  }
  flush();

  return phrases.filter((p) => p.text.length > 0);
};

export const Clip: React.FC<ClipProps> = ({
  videoSrc,
  headline,
  words,
  musicSrc,
  musicVolume,
  orientation,
  durationSec,
  videoAspect,
  bgBlurFill = false,
  headlineDurationSec = 0,
  hideCaptions = false,
  headlineStyle = "default",
  maskTop = false,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  const phrases = useMemo(
    () => (hideCaptions ? [] : buildPhrases(words || [])),
    [words, hideCaptions],
  );
  const activeIndex = useMemo(() => {
    let found = -1;
    for (let i = 0; i < phrases.length; i++) {
      if (phrases[i].start <= t) found = i;
      else break;
    }
    return found;
  }, [phrases, t]);

  let active: Phrase | undefined;
  if (activeIndex >= 0) {
    const candidate = phrases[activeIndex];
    const next = phrases[activeIndex + 1];
    const holdUntil = next
      ? Math.min(next.start, candidate.end + CAPTION_HOLD_S)
      : candidate.end + CAPTION_HOLD_S;
    if (t <= Math.max(candidate.end, holdUntil)) {
      active = candidate;
    }
  }

  const isPortrait = orientation === "portrait";
  const isPill = headlineStyle === "pill";
  const showHeadline =
    Boolean(headline && headline.trim()) &&
    (!headlineDurationSec || headlineDurationSec <= 0 || t < headlineDurationSec);

  // Landscape source letterboxes inside the 9:16 canvas at its true aspect,
  // which is not 16:9 when a burned-in subtitle band has been cropped off.
  const safeAspect = videoAspect && videoAspect > 0 ? videoAspect : 16 / 9;
  const videoHeight = isPortrait
    ? height
    : Math.min(height, Math.round(width / safeAspect));
  const videoTop = isPortrait ? 0 : Math.round((height - videoHeight) / 2);

  // Headline: top gradient band on portrait, bottom of the upper black bar on landscape.
  const headlineBottom = isPortrait ? undefined : height - videoTop + 40;
  const headlineTop = isPortrait ? 120 : undefined;
  // Captions: below the chin on portrait. On landscape they sit under the
  // picture, anchored to the bottom of the footage so a cropped (non-16:9) clip
  // keeps the same gap, but never pushed off the bottom of the canvas when the
  // picture is tall (square or 4:3 sources).
  const captionTop = isPortrait
    ? Math.round(height * 0.74)
    : Math.min(videoTop + videoHeight + 230, height - 260);

  const musicGain = () => {
    const fadeIn = interpolate(t, [0, FADE_IN], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    const fadeOut = interpolate(
      t,
      [Math.max(0, durationSec - FADE_OUT), durationSec],
      [1, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );
    return musicVolume * fadeIn * fadeOut;
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {/* Blurred backdrop: scaled copy of the same frame filling the dead
          letterbox space. MUST be muted, a second audio track would double
          the dialogue. Landscape only; portrait already fills the canvas. */}
      {bgBlurFill && !isPortrait ? (
        <AbsoluteFill style={{ overflow: "hidden" }}>
          <OffthreadVideo
            src={staticFile(videoSrc)}
            muted
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "blur(55px) saturate(1.2) brightness(0.45)",
              transform: "scale(1.3)",
            }}
          />
        </AbsoluteFill>
      ) : null}

      {/* Source video */}
      <AbsoluteFill
        style={{
          top: videoTop,
          height: videoHeight,
        }}
      >
        <OffthreadVideo
          src={staticFile(videoSrc)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      </AbsoluteFill>

      {/* Optional solid band that hides a headline already burned into the source */}
      {maskTop ? (
        <AbsoluteFill
          style={{
            height: isPortrait ? 330 : Math.max(videoTop, 330),
            backgroundColor: "#000000",
          }}
        />
      ) : null}

      {/* Portrait: dark gradient behind the headline so it stays legible over footage */}
      {isPortrait && showHeadline && !isPill && !maskTop ? (
        <AbsoluteFill
          style={{
            height: 420,
            background:
              "linear-gradient(to bottom, rgba(0,0,0,0.78) 0%, rgba(0,0,0,0.45) 55%, rgba(0,0,0,0) 100%)",
          }}
        />
      ) : null}

      {/* Headline */}
      {showHeadline ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: headlineTop,
            bottom: headlineBottom,
            paddingLeft: 72,
            paddingRight: 72,
            display: "flex",
            alignItems: isPortrait ? "flex-start" : "flex-end",
            justifyContent: "center",
          }}
        >
          <div
            style={
              {
                fontFamily: fontStack,
                fontWeight: 700,
                fontSize: 56,
                lineHeight: 1.18,
                color: isPill ? "#111111" : "#FFFFFF",
                backgroundColor: isPill ? "#FFFFFF" : "transparent",
                borderRadius: isPill ? 28 : 0,
                padding: isPill ? "22px 36px" : 0,
                textAlign: "center",
                textWrap: "balance",
                letterSpacing: "-0.01em",
                textShadow:
                  isPortrait && !isPill ? "0 2px 18px rgba(0,0,0,0.55)" : "none",
              } as React.CSSProperties
            }
          >
            {headline}
          </div>
        </div>
      ) : null}

      {/* Phrase captions */}
      {active ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: captionTop,
            paddingLeft: 64,
            paddingRight: 64,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <div
            style={
              {
                fontFamily: fontStack,
                fontWeight: 800,
                fontSize: 46,
                lineHeight: 1.2,
                color: "#FFFFFF",
                textAlign: "center",
                textWrap: "balance",
                textShadow:
                  "0 3px 10px rgba(0,0,0,0.85), 0 1px 3px rgba(0,0,0,0.95)",
              } as React.CSSProperties
            }
          >
            {active.text}
          </div>
        </div>
      ) : null}

      {/* Music underbed: pre-trimmed upstream, so it plays from 0 here */}
      {musicSrc ? (
        <Audio src={staticFile(musicSrc)} volume={musicGain()} />
      ) : null}
    </AbsoluteFill>
  );
};
