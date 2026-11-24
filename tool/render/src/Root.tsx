import React from "react";
import { Composition } from "remotion";
import { Clip, ClipProps, FPS } from "./Clip";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Clip"
      component={Clip}
      width={1080}
      height={1920}
      fps={FPS}
      durationInFrames={900}
      defaultProps={
        {
          videoSrc: "",
          headline: "headline goes here",
          words: [],
          musicSrc: null,
          musicVolume: 0.07,
          orientation: "landscape",
          durationSec: 30,
          videoAspect: 16 / 9,
        } as ClipProps
      }
      calculateMetadata={({ props }) => ({
        durationInFrames: Math.max(1, Math.round(props.durationSec * FPS)),
      })}
    />
  );
};
