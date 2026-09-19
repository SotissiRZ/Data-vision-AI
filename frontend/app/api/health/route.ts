export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json({
    status: 'ok',
    service: 'datavision-web',
    version: '2.29.0',
  });
}
