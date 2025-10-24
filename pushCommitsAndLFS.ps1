# --- Configuration ---
$TargetDirectory = "./earCrawler"
$SizeLimitBytes = 100 * 1024 * 1024  # 100 MB in bytes
$CommitMessage = "Track large files with LFS and commit changes"

# --- Step 1: Find Large Files and Unique Extensions ---

Write-Host "Searching for files larger than 100MB in '$TargetDirectory'..."

# Find all files larger than the limit recursively
$LargeFiles = Get-ChildItem -Path $TargetDirectory -File -Recurse | Where-Object { $_.Length -gt $SizeLimitBytes }

if (-not $LargeFiles) {
    Write-Host "No files found over 100MB. Proceeding with standard commit."
}
else {
    Write-Host "Found $($LargeFiles.Count) large files. Preparing to use Git LFS."

    # Extract unique file extensions (e.g., '.zip', '.bin')
    $UniqueExtensions = $LargeFiles | ForEach-Object { $_.Extension } | Select-Object -Unique | Where-Object { $_ -ne "" }

    if (-not $UniqueExtensions) {
        Write-Host "Large files found, but they have no extensions. You'll need to track them by filename manually."
    }
    else {
        # --- Step 2: Configure Git LFS Tracking ---
        Write-Host "Configuring Git LFS for the following extensions: $($UniqueExtensions -join ', ')..."
        
        # Track each unique extension
        foreach ($Extension in $UniqueExtensions) {
            # Trim the leading dot for the git lfs track command
            $Pattern = "*$Extension"
            Write-Host "Running: git lfs track '$Pattern'" -ForegroundColor Yellow
            # The '--' ensures no arguments are misinterpreted as options
            git lfs track -- $Pattern
            # Optional: Add .gitattributes to staging immediately
            git add .gitattributes
        }
    }
    
    Write-Host "LFS configuration complete. Please verify the '.gitattributes' file."
}

# --- Step 3: Add all changes ---
Write-Host "Staging all changes (including .gitattributes)..."
# 'git add .' will stage all modified, deleted, and new files, 
# including those now tracked by LFS and the .gitattributes file.
git add . 

# --- Step 4: Commit the changes ---
Write-Host "Committing changes with message: '$CommitMessage'..."
# Use -m to specify the commit message
git commit -m $CommitMessage

# --- Step 5: Push the changes ---
Write-Host "Pushing changes to remote repository..."
# Assumes your remote is 'origin' and branch is your current one
git push --force origin main
Write-Host "Operation complete. Check your Git status and remote repository."