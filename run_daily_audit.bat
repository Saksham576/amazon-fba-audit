@echo off
REM Autonomous Daily Amazon FBA Inventory Reconciliation & Payout Daemon
REM Runs unattended 24/7 via Windows Task Scheduler.
REM Consumes 0 LLM tokens, executes deterministic Python engine.

cd /d "C:\Users\saksh\teamwork_projects\amazon_fba_audit"

echo ======================================================== >> "payouts\daemon_run.log"
echo [FBA AUDIT DAEMON] Started at %DATE% %TIME% >> "payouts\daemon_run.log"
echo ======================================================== >> "payouts\daemon_run.log"

".venv\Scripts\fba-daemon.exe" --once --simulate-if-empty >> "payouts\daemon_run.log" 2>&1

echo [FBA AUDIT DAEMON] Finished at %DATE% %TIME% >> "payouts\daemon_run.log"
echo. >> "payouts\daemon_run.log"
