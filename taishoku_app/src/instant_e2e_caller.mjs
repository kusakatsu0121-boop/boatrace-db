import crypto from 'node:crypto';
import http from 'node:http';

const target = String(process.env.TARGET_URL || 'https://taishoku-instant-web-report-test.onrender.com').replace(/\/+$/, '');
const port = Number(process.env.PORT || 10000);

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  res.end(JSON.stringify({ status: 'ok', role: 'isolated-instant-e2e-caller' }));
});

server.listen(port, '0.0.0.0', () => {
  console.log(JSON.stringify({ status: 'caller_listening', port, target }));
  run().catch(error => {
    console.error(JSON.stringify({ status: 'instant_e2e_failed', error: error.message || String(error) }));
  });
});

function choice(key, label, id, text, type = 'MULTIPLE_CHOICE') {
  return { key, type, label, value: [id], options: [{ id, text }] };
}

async function sleep(ms) {
  await new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
  const token = crypto.randomBytes(32).toString('base64url');
  const stamp = Date.now();
  const responseId = `INSTANTE2E${stamp}`;
  const createdAt = new Date().toISOString();
  const fields = [
    { key: 'f6459a23-198b-485f-a76e-dd3bb2daa6ea', type: 'INPUT_TEXT', label: 'レポートに表示するニックネームを入力してください', value: 'Instant-E2E' },
    { key: 'b35166f9-990b-4e4c-89c4-2c56defafe77', type: 'INPUT_EMAIL', label: '納品先メールアドレス', value: 'instant-e2e@example.com' },
    choice('7b83690e-7554-4279-b34a-9aed960d5a0e', '現在の状態に最も近いもの', '08851faa-cc91-49c0-8263-ae159fbdc37c', 'すでに退職した'),
    choice('a497578d-0f64-42ea-ba39-212afdf2a85b', '今の仕事を続けることや、休職・退職を考えるきっかけになっていることを選んでください。※いくつ選んでも構いません。', '89f72730-3e8a-490e-8f93-6c7eff16cd16', '仕事内容が合わない・今後のキャリア', 'CHECKBOXES'),
    choice('ca2dcdc1-78e0-4aa5-80bd-62b7046dec0d', '体調などを考えると、次の仕事は始められそうですか？', '9fac756c-1c16-4d4a-8e0d-d800945737cd', '始められそう', 'DROPDOWN'),
    { key: '3f63703e-475e-4c46-8728-1189e665307e', type: 'INPUT_NUMBER', label: '退職時の年齢', value: 42 },
    choice('18238c9c-3b3d-4f52-9af1-89ccf0a43020', '雇用保険に加入して働いた期間', 'eb3eee42-e1d4-41be-8539-83e074bdd075', '1年以上5年未満', 'DROPDOWN'),
    { key: '09450e73-9117-4077-bd7c-51298550017e', type: 'INPUT_DATE', label: '退職日', value: '2026-08-01' },
    choice('dd7bb653-ee89-4c54-91ef-39794ced708d', '会社や窓口から、返答・署名・提出などの期限を示されていますか？', 'ee477d3c-89a6-4547-81db-159a581e1703', 'ない'),
    choice('ed57d9e6-9a51-431b-9d93-20183e41352b', '離職票は届いていますか？', '49ad2265-7d70-4488-a34f-20ea4afe7d1d', 'まだ届いていない'),
    choice('47568c87-3082-4b72-9352-4d0b402d9704', '選んだ理由の中で、一番大きな理由を1つ選んでください', '1fb337e0-8f03-4e81-986e-83cb9b65afcf', 'キャリア・仕事内容'),
    choice('f4ec527c-7757-43c3-a787-9f3acc2b17c5', '退職日に出勤しましたか、または出勤する予定ですか？', 'cc386f6d-2aa9-471d-a1d8-583c0328e04c', '出勤していない・出勤しない予定'),
    choice('a278285f-708a-49e2-a305-5ff63d6911c9', 'この先、仕事についてどう考えていますか？', '9a6840f0-05a5-477c-98b3-587ed2de1a1c', '仕事を探すつもり'),
    choice('a1509f23-1bfc-47c3-a1cb-6865ca099f3f', '退職前6か月の賃金の入力方法を選んでください', '7db6bb6a-cd6a-42ed-8bd4-1da2d732c0c1', '6か月分の合計額を入力する'),
    { key: '541e0cfe-1608-4773-a21f-652bd0bec4d4', type: 'INPUT_NUMBER', label: '6か月分の合計額を入力してください', value: 1800000 },
    choice('5de35d76-8705-4d28-b0c8-f461cee523bf', '今回のレポートで、特に知りたい・整理したいことを選んでください。', 'fb1ca33c-09eb-4aa5-9b21-0a8456968a98', '失業手当の金額と受け取り方', 'CHECKBOXES'),
    choice('46b66790-089c-496b-b115-05fbd57b1217', '連続する3日間を含め、4日以上仕事に就けなかった期間がありますか？', '4265ae9b-5390-40fa-9df0-7980c3a48c2f', 'いいえ'),
    choice('d97182b8-174d-4708-b601-e9f96aa4ea19', '現在、手元にあるものを選んでください', '2ac6783d-dd6f-4c39-88ed-3bed79d3aba6', '特にない', 'CHECKBOXES'),
    { key: '3452a118-280d-47e3-bc28-f6db09786c8d', type: 'TEXTAREA', label: 'そのほか伝えておきたいこと', value: 'Instant E2E test。実在利用者ではありません。納品不要。' },
    choice('890e6e05-b0a9-4ea4-b1cb-2313d168456c', 'ご利用上の確認事項', 'd6d593f6-fbad-473d-9161-9df767057f2a', '回答内容をもとに、個別レポートを作成することに同意します。\n給与や離職理由の最終決定、申請代行、会社との交渉を行うサービスではないことを確認しました。', 'CHECKBOXES'),
  ];

  const payload = {
    eventId: `instant-e2e-${stamp}`,
    eventType: 'FORM_RESPONSE',
    createdAt,
    data: {
      formId: 'QKyVpY',
      formName: 'あなた専用｜退職前後ワークフロー',
      createdAt,
      responseId,
      submissionId: responseId,
      respondentId: 'instant-e2e',
      instant_token: token,
      fields,
    },
  };

  console.log(JSON.stringify({ status: 'instant_e2e_posting', response_id: responseId, report_url: `${target}/r/${token}` }));
  const response = await fetch(`${target}/webhooks/tally`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await response.text();
  console.log(JSON.stringify({ status: 'instant_e2e_webhook_response', http_status: response.status, body: body.slice(0, 1000) }));
  if (![200, 202].includes(response.status)) throw new Error(`webhook_http_${response.status}`);

  const reportUrl = `${target}/r/${token}`;
  for (let attempt = 1; attempt <= 60; attempt += 1) {
    const report = await fetch(reportUrl, { redirect: 'manual' });
    const html = await report.text();
    if (report.status === 200 && !html.includes('レポートを作成しています')) {
      console.log(JSON.stringify({ status: 'instant_e2e_complete', response_id: responseId, report_url: reportUrl, http_status: report.status, contains_display_name: html.includes('Instant-E2E'), automatic_delivery: false }));
      return;
    }
    if (attempt === 1 || attempt % 5 === 0) {
      console.log(JSON.stringify({ status: 'instant_e2e_waiting', attempt, http_status: report.status }));
    }
    await sleep(2000);
  }
  throw new Error('report_timeout');
}
