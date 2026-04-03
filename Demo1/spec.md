Technical Specification: Stochastic Character Grid (Demo1)
Project Root: D:\Projects\AppFactory\Demo1

Stack: Python 3.12+, Pygame CE

Theme: Retro Terminal / Digital Noise

1. Core Logic & Data Structure
Grid State: Maintain a 2D array (or list of lists) of Cell objects.

Cell Properties:

char: Current alphanumeric character (a-z, 0-9).

color: Current RGB tuple.

next_char_time: Timestamp (float) for the next character flip.

next_color_time: Timestamp (float) for the next color change.

Randomized Intervals: When a change occurs, the next interval must be a random float between 0.5s and 2.0s, recalculated independently for char and color.

2. Dynamic Window Management
Resizable Window: The app must listen for VIDEORESIZE events.

Adaptive Grid: On resize, recalculate the number of columns and rows based on the current window dimensions and a fixed font size (e.g., 20px).

Center Alignment: Ensure the grid fills the space edge-to-edge.

3. Rendering Engine (Canvas-based)
Font: Use a monospaced system font (e.g., "Courier", "Consolas", or "Monospace").

High-Frequency Loop: Use a standard Pygame while loop running at 60 FPS.

Performance Optimization: Use font.render() to create surfaces. For extreme performance at high densities, Gemini should implement a font cache (pre-rendering all 36 characters) so it only has to "blit" images instead of re-rendering text every frame.

4. Execution Steps for Gemini Assist
Environment Setup: Create a requirements.txt with pygame-ce.

Boilerplate: Initialize a resizable Pygame window with a dark background.

The Grid Logic: Implement the Cell class and the logic to populate/re-populate the grid on resize.

The Update Loop: Implement the timestamp-based comparison (if current_time > cell.next_char_time) to trigger changes without using heavy Python threads.