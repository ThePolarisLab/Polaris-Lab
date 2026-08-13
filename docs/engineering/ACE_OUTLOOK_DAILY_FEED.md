# ACE Outlook Daily Feed

Status: manual-first integration

Polaris ACE imports the scheduled CBP ACE recurring report delivered to the connected Outlook mailbox. The current source is the In-Bond `[unx] -> In-Bond Bills of Lading` report. Standalone Manifest ingestion remains deferred.

## Source Contract

- Subject: `MOR ACE Daily In-Bond Report`
- Attachment type: `.xlsx`
- Worksheet: `Report 1`
- Header row: Excel row 4
- Column A: blank/tolerated
- Data columns: begin at column B
- Movement identity: organization + In-Bond Number + Bill of Lading Number
- Import identity: organization + Outlook source message ID

Verified raw headers:

1. `In-Bond Number`
2. `Bill of Lading Number`
3. `In-Bond Type Code`
4. `In-Bond Type Description`
5. `In-Bond Source Type Description`
6. `In-Bond Record Status Name`
7. `In-Bond Carrier Code`
8. `In-Bond Carrier Name`
9. `Manifest Carrier Code`
10. `Manifest Carrier Name`
11. `QP Filer Code`
12. `QP Filer Name`
13. `Shipper Name`
14. `Consignee Name`
15. `Origination Port Name`
16. `In-Bond Create Date`
17. `In-Bond Arrival Date`
18. `Destination Port Name`
19. `Export Date`
20. `Days Late`
21. `Days Overdue for Export`
22. `Late In-Transit Indicator`
23. `Overdue for Export Indicator`
24. `Transfer of Liability Date/Time`

`Penalty Indicator` is not present in the verified scheduled file. Polaris treats it as unreported and does not infer a penalty value from this feed.

## Operational Boundary

The Outlook connector remains read-only under delegated `Mail.Read`. The ACE feed retrieves the qualifying attachment content only for the manual import action, parses it transiently, and does not store raw email bodies or raw attachment bytes.

The manual endpoint searches a bounded recent Outlook window, selects the newest exact-subject report with one supported XLSX attachment, skips successfully imported source messages, parses the workbook in memory, and invokes the existing ACE import service directly.

Daily Brief remains exception-only. Carrier mismatch and watched QP filer activity create review population only; unauthorized status remains a manual management classification. Manual authorization decisions, evidence references, resolution notes, and resolved history are preserved across daily imports.

Recurring scheduling remains deferred until after controlled production verification of one import and one replay of the same source message.
