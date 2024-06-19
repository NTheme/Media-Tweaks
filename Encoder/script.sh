#!/bin/bash
ffmpeg -hwaccel cuda -i $1 -c:v h264_nvenc -b:v 60M -ac 1 $2
