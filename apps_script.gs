// Resume Tailor tracker. Paste into Extensions > Apps Script of "Job Applications Tracker".
// Set this to a long random string, and put the SAME value in tracker_config.json as "token". Never commit the real value.
const TOKEN = 'CHANGE_ME_TO_A_LONG_RANDOM_STRING';
const FOLDER_ID = '1uDlna0gPeNSj56P6hW6H673E1AWjauqC';   // "Resume Tailor" folder
const SHEET_ID = '10_DQh2vbybANN7uFN_-xjEs0x06-4DwNaPjoeUTjZvc';
const HEADERS = ['Company', 'Role', 'Resume'];

function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.token !== TOKEN) return out({ ok: false, error: 'bad token' });

    // PDFs live in a "Resumes" subfolder of the Resume Tailor folder (created if missing)
    const parent = DriveApp.getFolderById(FOLDER_ID);
    const it = parent.getFoldersByName('Resumes');
    const folder = it.hasNext() ? it.next() : parent.createFolder('Resumes');
    const blob = Utilities.newBlob(Utilities.base64Decode(d.pdf_base64), 'application/pdf', d.filename);
    const file = folder.createFile(blob);

    const sheet = SpreadsheetApp.openById(SHEET_ID).getSheets()[0];
    ensureLayout(sheet);
    sheet.appendRow([d.company, d.role, '=HYPERLINK("' + file.getUrl() + '","' + d.filename.replace(/"/g, '') + '")']);
    return out({ ok: true, drive_url: file.getUrl() });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

// Keeps the sheet to exactly Company | Role | Resume. Old layouts are cleared once.
function ensureLayout(sheet) {
  const first = sheet.getRange(1, 1, 1, 3).getValues()[0];
  if (first.join('|') === HEADERS.join('|') && sheet.getLastColumn() <= 3) return;
  sheet.clear();
  if (sheet.getMaxColumns() > 3) sheet.deleteColumns(4, sheet.getMaxColumns() - 3);
  sheet.getRange(1, 1, 1, 3).setValues([HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(1, 180);
  sheet.setColumnWidth(2, 320);
  sheet.setColumnWidth(3, 420);
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
