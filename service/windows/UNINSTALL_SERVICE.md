To remove the `EarCrawler-API` Windows service created with NSSM:

1. Stop the service if it is running:

    ```powershell
    C:\tools\nssm\nssm.exe stop EarCrawler-API
    ```

2. Remove the service definition:

    ```powershell
    C:\tools\nssm\nssm.exe remove EarCrawler-API confirm
    ```

3. Delete any log files or working directories under
   `C:\ProgramData\EarCrawler\` if they are no longer required.
