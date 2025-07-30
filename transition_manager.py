#!/usr/bin/env python3
"""
Transition Manager for Video Generation Pipeline
Adds random crossfades and wipes between slides for smoother video transitions
"""

import os
import json
import random
from typing import List, Dict, Tuple, Optional
from moviepy.editor import VideoFileClip, CompositeVideoClip, VideoClip, concatenate_videoclips
from moviepy.video.fx.all import resize, fadein, fadeout
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def print_flush(*args, **kwargs):
    """Print with immediate flush to ensure output is visible"""
    print(*args, **kwargs, flush=True)

class TransitionManager:
    """
    Manages smooth transitions between video slides.
    Supports multiple transition types and can be configured per slide.
    """
    
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        
        # Transition types available
        self.transition_types = {
            'fade': self._create_fade_transition,
            'slide_left': self._create_slide_left_transition,
            'slide_right': self._create_slide_right_transition,
            'slide_up': self._create_slide_up_transition,
            'slide_down': self._create_slide_down_transition,
            'zoom_in': self._create_zoom_in_transition,
            'zoom_out': self._create_zoom_out_transition,
            'dissolve': self._create_dissolve_transition,
            'wipe_left': self._create_wipe_left_transition,
            'wipe_right': self._create_wipe_right_transition,
            'wipe_up': self._create_wipe_up_transition,
            'wipe_down': self._create_wipe_down_transition,
            'crossfade': self._create_crossfade_transition,
            'none': self._create_no_transition
        }
        
        # Default transition settings
        self.default_transition = 'fade'
        self.default_duration = 0.5  # seconds
        self.transition_duration = self.default_duration
        
    def set_transition_duration(self, duration: float):
        """Set the duration for transitions"""
        self.transition_duration = duration
        
    def get_random_transition(self) -> str:
        """Get a random transition type"""
        return random.choice(list(self.transition_types.keys()))
    
    def get_transition_for_slide(self, slide_dict: Dict, previous_slide_dict: Optional[Dict] = None) -> str:
        """
        Determine the best transition type for a slide based on its format and content.
        This can be customized based on slide format, content, or other factors.
        """
        format_type = slide_dict.get('format', 2)
        
        # Format-specific transitions
        if format_type == 4:  # Full image slides
            # Use more dramatic transitions for image-heavy slides
            return random.choice(['fade', 'zoom_in', 'zoom_out', 'dissolve'])
        elif format_type in [2, 3]:  # Text + image slides
            # Use directional transitions that complement the layout
            if format_type == 2:  # Left text, right image
                return random.choice(['slide_left', 'slide_right', 'fade', 'crossfade'])
            else:  # Right text, left image
                return random.choice(['slide_left', 'slide_right', 'fade', 'crossfade'])
        else:
            # Default transitions
            return random.choice(['fade', 'slide_left', 'slide_right', 'crossfade'])
    
    def _create_no_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """No transition - return clip as is"""
        return clip
    
    def _create_fade_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a fade in/out transition"""
        return clip.fadein(duration).fadeout(duration)
    
    def _create_slide_left_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a slide transition from right to left"""
        def slide_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Slide from right to left
                progress = t / duration
                offset = int(self.width * (1 - progress))
                new_frame = np.zeros_like(frame)
                new_frame[:, :offset] = frame[:, (self.width - offset):]
                return new_frame
            return frame
        
        return clip.fl(slide_effect)
    
    def _create_slide_right_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a slide transition from left to right"""
        def slide_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Slide from left to right
                progress = t / duration
                offset = int(self.width * progress)
                new_frame = np.zeros_like(frame)
                new_frame[:, offset:] = frame[:, :(self.width - offset)]
                return new_frame
            return frame
        
        return clip.fl(slide_effect)
    
    def _create_slide_up_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a slide transition from bottom to top"""
        def slide_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Slide from bottom to top
                progress = t / duration
                offset = int(self.height * (1 - progress))
                new_frame = np.zeros_like(frame)
                new_frame[:offset, :] = frame[(self.height - offset):, :]
                return new_frame
            return frame
        
        return clip.fl(slide_effect)
    
    def _create_slide_down_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a slide transition from top to bottom"""
        def slide_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Slide from top to bottom
                progress = t / duration
                offset = int(self.height * progress)
                new_frame = np.zeros_like(frame)
                new_frame[offset:, :] = frame[:(self.height - offset), :]
                return new_frame
            return frame
        
        return clip.fl(slide_effect)
    
    def _create_zoom_in_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a zoom in transition"""
        def zoom_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Zoom in from center
                progress = t / duration
                scale = 0.5 + 0.5 * progress
                new_size = (int(self.width * scale), int(self.height * scale))
                # Resize frame
                from PIL import Image
                pil_img = Image.fromarray(frame)
                pil_img = pil_img.resize(new_size, Image.LANCZOS)
                # Crop to original size from center
                left = (new_size[0] - self.width) // 2
                top = (new_size[1] - self.height) // 2
                pil_img = pil_img.crop((left, top, left + self.width, top + self.height))
                return np.array(pil_img)
            return frame
        
        return clip.fl(zoom_effect)
    
    def _create_zoom_out_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a zoom out transition"""
        def zoom_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Zoom out from center
                progress = t / duration
                scale = 1.0 - 0.3 * progress
                new_size = (int(self.width * scale), int(self.height * scale))
                # Resize frame
                from PIL import Image
                pil_img = Image.fromarray(frame)
                pil_img = pil_img.resize(new_size, Image.LANCZOS)
                # Create new frame with black background
                new_frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                # Paste resized image in center
                left = (self.width - new_size[0]) // 2
                top = (self.height - new_size[1]) // 2
                new_frame[top:top + new_size[1], left:left + new_size[0]] = np.array(pil_img)
                return new_frame
            return frame
        
        return clip.fl(zoom_effect)
    
    def _create_dissolve_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a dissolve transition (similar to crossfade but more gradual)"""
        return clip.fadein(duration * 0.7).fadeout(duration * 0.3)
    
    def _create_wipe_left_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a wipe transition from right to left"""
        def wipe_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Wipe from right to left
                progress = t / duration
                wipe_line = int(self.width * (1 - progress))
                new_frame = np.zeros_like(frame)
                new_frame[:, :wipe_line] = frame[:, :wipe_line]
                return new_frame
            return frame
        
        return clip.fl(wipe_effect)
    
    def _create_wipe_right_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a wipe transition from left to right"""
        def wipe_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Wipe from left to right
                progress = t / duration
                wipe_line = int(self.width * progress)
                new_frame = np.zeros_like(frame)
                new_frame[:, wipe_line:] = frame[:, wipe_line:]
                return new_frame
            return frame
        
        return clip.fl(wipe_effect)
    
    def _create_wipe_up_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a wipe transition from bottom to top"""
        def wipe_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Wipe from bottom to top
                progress = t / duration
                wipe_line = int(self.height * (1 - progress))
                new_frame = np.zeros_like(frame)
                new_frame[:wipe_line, :] = frame[:wipe_line, :]
                return new_frame
            return frame
        
        return clip.fl(wipe_effect)
    
    def _create_wipe_down_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a wipe transition from top to bottom"""
        def wipe_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # Wipe from top to bottom
                progress = t / duration
                wipe_line = int(self.height * progress)
                new_frame = np.zeros_like(frame)
                new_frame[wipe_line:, :] = frame[wipe_line:, :]
                return new_frame
            return frame
        
        return clip.fl(wipe_effect)
    
    def _create_crossfade_transition(self, clip: VideoClip, duration: float) -> VideoClip:
        """Create a crossfade transition"""
        return clip.fadein(duration).fadeout(duration)
    
    def apply_transition_to_clip(self, clip: VideoClip, transition_type: str = None, duration: float = None) -> VideoClip:
        """
        Apply a transition effect to a video clip.
        
        Args:
            clip: The video clip to apply transition to
            transition_type: Type of transition to apply (if None, uses default)
            duration: Duration of transition (if None, uses default)
            
        Returns:
            VideoClip with transition applied
        """
        if transition_type is None:
            transition_type = self.default_transition
        if duration is None:
            duration = self.transition_duration
            
        if transition_type not in self.transition_types:
            print_flush(f"Warning: Unknown transition type '{transition_type}', using 'fade'")
            transition_type = 'fade'
            
        transition_func = self.transition_types[transition_type]
        return transition_func(clip, duration)
    
    def create_transition_between_clips(self, clip1: VideoClip, clip2: VideoClip, 
                                      transition_type: str = None, duration: float = None) -> VideoClip:
        """
        Create a smooth transition between two video clips.
        
        Args:
            clip1: First video clip
            clip2: Second video clip
            transition_type: Type of transition to use
            duration: Duration of transition
            
        Returns:
            CompositeVideoClip with transition
        """
        if transition_type is None:
            transition_type = self.default_transition
        if duration is None:
            duration = self.transition_duration
            
        # For crossfade, we need to overlap the clips
        if transition_type == 'crossfade':
            # Set the second clip to start before the first one ends
            clip2 = clip2.set_start(clip1.duration - duration)
            return CompositeVideoClip([clip1, clip2])
        
        # For other transitions, we can concatenate with transition effects
        clip1_with_transition = self.apply_transition_to_clip(clip1, transition_type, duration)
        clip2_with_transition = self.apply_transition_to_clip(clip2, transition_type, duration)
        
        return concatenate_videoclips([clip1_with_transition, clip2_with_transition])
    
    def process_video_clips_with_transitions(self, clips: List[VideoClip], 
                                           transition_types: List[str] = None,
                                           transition_duration: float = None) -> VideoClip:
        """
        Process a list of video clips and add transitions between them.
        
        Args:
            clips: List of video clips to process
            transition_types: List of transition types for each transition (if None, auto-selects)
            transition_duration: Duration for all transitions (if None, uses default)
            
        Returns:
            Single VideoClip with all transitions applied
        """
        import time
        import psutil
        
        print_flush(f"[TRANSITION DEBUG] Starting transition processing for {len(clips)} clips")
        print_flush(f"[TRANSITION DEBUG] Memory usage: {psutil.virtual_memory().percent}%")
        transition_start = time.time()
        
        if not clips:
            print_flush("[TRANSITION DEBUG] No clips provided, returning None")
            return None
            
        if len(clips) == 1:
            print_flush("[TRANSITION DEBUG] Single clip, returning as-is")
            return clips[0]
            
        if transition_duration is None:
            transition_duration = self.transition_duration
        print_flush(f"[TRANSITION DEBUG] Using transition duration: {transition_duration}s")
            
        # Auto-select transition types if not provided
        if transition_types is None:
            print_flush("[TRANSITION DEBUG] Auto-selecting transition types...")
            transition_types = [self.get_random_transition() for _ in range(len(clips) - 1)]
            print_flush(f"[TRANSITION DEBUG] Selected transitions: {transition_types}")
        elif len(transition_types) < len(clips) - 1:
            # Pad with random transitions if not enough provided
            print_flush("[TRANSITION DEBUG] Padding transition types...")
            while len(transition_types) < len(clips) - 1:
                transition_types.append(self.get_random_transition())
            print_flush(f"[TRANSITION DEBUG] Final transitions: {transition_types}")
        
        print_flush(f"[TRANSITION DEBUG] Processing {len(clips)} clips with transitions...")
        
        # Apply transitions between clips
        result_clips = []
        for i, clip in enumerate(clips):
            clip_start = time.time()
            print_flush(f"[TRANSITION DEBUG] Processing clip {i+1}/{len(clips)}, duration: {clip.duration}s")
            
            if i == 0:
                # First clip - apply fade in
                print_flush(f"[TRANSITION DEBUG] Applying fadein to first clip...")
                clip_with_transition = clip.fadein(transition_duration)
                print_flush(f"[TRANSITION DEBUG] First clip processed in {time.time() - clip_start:.2f}s")
            elif i == len(clips) - 1:
                # Last clip - apply fade out
                print_flush(f"[TRANSITION DEBUG] Applying fadeout to last clip...")
                clip_with_transition = clip.fadeout(transition_duration)
                print_flush(f"[TRANSITION DEBUG] Last clip processed in {time.time() - clip_start:.2f}s")
            else:
                # Middle clips - apply both fade in and out
                print_flush(f"[TRANSITION DEBUG] Applying fadein/fadeout to middle clip...")
                clip_with_transition = clip.fadein(transition_duration).fadeout(transition_duration)
                print_flush(f"[TRANSITION DEBUG] Middle clip processed in {time.time() - clip_start:.2f}s")
            
            result_clips.append(clip_with_transition)
            print_flush(f"[TRANSITION DEBUG] Added clip {i+1} to result list")
        
        print_flush(f"[TRANSITION DEBUG] All clips processed, concatenating {len(result_clips)} clips...")
        print_flush(f"[TRANSITION DEBUG] Memory usage before concatenation: {psutil.virtual_memory().percent}%")
        
        concat_start = time.time()
        try:
            final_video = concatenate_videoclips(result_clips)
            concat_time = time.time() - concat_start
            print_flush(f"[TRANSITION DEBUG] Concatenation completed in {concat_time:.2f}s")
            print_flush(f"[TRANSITION DEBUG] Final video duration: {final_video.duration}s")
        except Exception as e:
            print_flush(f"[TRANSITION DEBUG][ERROR] Concatenation failed: {e}")
            raise
        
        total_time = time.time() - transition_start
        print_flush(f"[TRANSITION DEBUG] Transition processing completed in {total_time:.2f}s")
        print_flush(f"[TRANSITION DEBUG] Memory usage after processing: {psutil.virtual_memory().percent}%")
        
        return final_video
    
    def create_slide_transition_config(self, slides: List[Dict]) -> List[Dict]:
        """
        Create a transition configuration for a list of slides.
        This can be used to customize transitions based on slide content.
        
        Args:
            slides: List of slide dictionaries from slides.json
            
        Returns:
            List of transition configurations
        """
        transition_configs = []
        
        for i, slide in enumerate(slides):
            config = {
                'slide_number': slide.get('slide_number', i + 1),
                'transition_type': self.get_transition_for_slide(slide),
                'duration': self.transition_duration,
                'format': slide.get('format', 2)
            }
            transition_configs.append(config)
            
        return transition_configs
    
    def save_transition_config(self, transition_configs: List[Dict], output_path: str):
        """Save transition configuration to a JSON file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(transition_configs, f, indent=2, ensure_ascii=False)
    
    def load_transition_config(self, config_path: str) -> List[Dict]:
        """Load transition configuration from a JSON file"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f) 