# script to create a video from images
# delete all files in ./frames/
rm -rf ./frames/*
# run getImages.py until it is done
python3 getImages.py

# Create a 2-second video of the first frame
first_frame=$(ls -1 ./frames/ | head -n 1)
ffmpeg -y -t 2 -framerate 1 -i ./frames/$first_frame -c:v libx264 -pix_fmt yuv420p output_first_frame.mp4

# Create a 2-second video of the last frame
last_frame=$(ls -1 ./frames/ | tail -n 1)
ffmpeg -y -t 2 -framerate 1 -i ./frames/$last_frame -c:v libx264 -pix_fmt yuv420p output_last_frame.mp4

# Create video of all frames (middle frames)
ffmpeg -y -framerate 8 -i ./frames/%04d.png -c:v libx264 -pix_fmt yuv420p middleoutput.mp4

# Create a file list for concat (to avoid problems with different encoding settings)
echo "file 'output_first_frame.mp4'" > filelist.txt
echo "file 'middleoutput.mp4'" >> filelist.txt
echo "file 'output_last_frame.mp4'" >> filelist.txt

# Concatenate all the videos (first frame, middle frames, last frame)
ffmpeg -y -f concat -safe 0 -i filelist.txt -c copy tempoutput.mp4

# Resize the background image to 9:16 format (assuming background.png exists)
# ffmpeg -y -i background.png -vf "crop=in_h:in_h*16/9:0:0,scale=1080:1920,setsar=1" background_resized.png

# resize the tempoutput.mp4 to 1000x1000 format
# ffmpeg -y -i tempoutput.mp4 -vf "scale=1000:1000,setsar=1" resized_tempoutput.mp4

# overlay the video onto the background image
ffmpeg -y -i background.png -i tempoutput.mp4 -filter_complex "[0:v][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2" output.mp4

# Add text to the top of the video
ffmpeg -y -i output.mp4 -vf "[in]drawtext=text='Find the best move!':fontcolor=white:fontsize=100:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=50, drawtext=text='Pause to solve':fontcolor=white:fontsize=100:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=50+100" final_output.mp4

# Add logo to the bottom of the video
ffmpeg -y -i final_output.mp4 -i logo.png -filter_complex "[0:v][1:v]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)" final_output_with_logo.mp4

# Clean up (optional)
rm filelist.txt
rm tempoutput.mp4
# rm resized_tempoutput.mp4
rm output.mp4
rm final_output.mp4
rm output_first_frame.mp4
rm output_last_frame.mp4
rm middleoutput.mp4
