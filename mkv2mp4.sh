#!/bin/bash

# Use the provided argument for the directory, or fallback to the default directory
MONITOR_DIR_PATH="${1:-assets}"
PRESET_FILE_PATH="H264 NVENC CQ27.json"
echo "Monitoring MKV files in $MONITOR_DIR_PATH"

while true; do
    file_found=false
    while IFS= read -r -d '' input_file_path; do
        output_file_path="${input_file_path%.*}.mp4"
        if [[ ! -f "$output_file_path" ]]; then
            file_found=true
            echo "New file detected: $input_file_path"
            HandBrakeCLI --preset-import-file "$PRESET_FILE_PATH" -i "$input_file_path" -o "$output_file_path"
            if [[ $? -eq 0 ]]; then
                echo "Conversion successful: $output_file_path"
            else
                echo "Conversion failed for: $input_file_path"
            fi
        fi
    done < <(find "$MONITOR_DIR_PATH" -name "*.mkv" -print0)
    if [ "$file_found" = false ]; then
        echo "No new file detected. Sleeping for 60 seconds..."
        sleep 60
    fi
done
