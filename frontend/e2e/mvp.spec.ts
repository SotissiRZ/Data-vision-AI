import { expect, test } from '@playwright/test';

const API = '/api/backend';

test('@mvp deployed core analytics workflow through frontend proxy', async ({ request }) => {
  const csv = [
    'group,x,y,missing',
    'A,1,2,1',
    'A,2,4,',
    'B,3,6,3',
    'B,4,8,',
    'A,5,10,5',
    'B,6,12,6',
  ].join('\n');

  const uploaded = await request.post(`${API}/datasets`, {
    multipart: {
      file: {
        name: 'mvp-e2e.csv',
        mimeType: 'text/csv',
        buffer: Buffer.from(csv, 'utf-8'),
      },
    },
  });
  expect(uploaded.ok()).toBeTruthy();
  const datasetId = (await uploaded.json()).dataset.id as string;

  const profile = await request.get(`${API}/datasets/${datasetId}/profile`);
  expect(profile.ok()).toBeTruthy();
  expect((await profile.json()).rows).toBe(6);

  const quality = await request.get(`${API}/datasets/${datasetId}/quality`);
  expect(quality.ok()).toBeTruthy();
  expect((await quality.json()).issues_count).toBeGreaterThan(0);

  const transformed = await request.post(`${API}/datasets/${datasetId}/transform`, {
    data: { operation: { type: 'fill_missing', column: 'missing', strategy: 'median' } },
  });
  expect(transformed.ok()).toBeTruthy();
  const transformedBody = await transformed.json();
  const transformedId = transformedBody.dataset.id as string;
  expect(transformedBody.dataset.version).toBe(2);

  const correlations = await request.post(`${API}/datasets/${transformedId}/analysis/correlations`, {
    data: { columns: ['x', 'y'], method: 'pearson' },
  });
  expect(correlations.ok()).toBeTruthy();

  const visualization = await request.post(`${API}/datasets/${transformedId}/visualizations/build`, {
    data: { chart_type: 'scatter', x: 'x', y: 'y', aggregation: 'none', bins: 20 },
  });
  expect(visualization.ok()).toBeTruthy();
  expect((await visualization.json()).type).toBe('scatter');

  const analysis = await request.post(`${API}/datasets/${transformedId}/ai/analyze`, {
    data: {
      question: 'Analyse les corrélations entre x et y',
      variables: ['x', 'y'],
      mode: 'fast',
    },
  });
  expect(analysis.ok()).toBeTruthy();
  const analysisBody = await analysis.json();
  expect(analysisBody.critic.status).toBe('passed');

  const history = await request.get(`${API}/datasets/${transformedId}/ai/history`);
  expect(history.ok()).toBeTruthy();
  expect((await history.json()).count).toBe(1);

  const report = await request.post(`${API}/datasets/${transformedId}/reports`, {
    data: {
      title: 'MVP E2E',
      sections: ['overview', 'quality', 'descriptive', 'methodology', 'provenance'],
      analysis_session_id: analysisBody.session_id,
    },
  });
  expect(report.ok()).toBeTruthy();
  const reportId = (await report.json()).id as string;

  const exported = await request.get(`${API}/datasets/${transformedId}/reports/${reportId}/export/html`);
  expect(exported.ok()).toBeTruthy();
  expect(exported.headers()['content-type']).toContain('text/html');
});
