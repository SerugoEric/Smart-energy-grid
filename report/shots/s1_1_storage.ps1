# Section 1.1 screenshot: storage type.
Get-PhysicalDisk |
    Select-Object FriendlyName, MediaType, BusType, Size |
    Format-Table -AutoSize |
    Out-String -Width 120

Get-Volume -DriveLetter C |
    Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining |
    Format-Table -AutoSize |
    Out-String -Width 120
