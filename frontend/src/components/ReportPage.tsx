import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

interface ReportData {
  username: string;
  full_name: string;
  email: string;
  country: string;
  signals_total: number;
  prosthesis_types: number;
  avg_signal_amplitude: string | number | null;
  avg_signal_duration: number | null;
  period_start: string | null;
  period_end: string | null;
}

interface ReportMeta {
  username: string;
  status: 'ready' | 'no_data';
  source?: 's3' | 'olap';
  url?: string;
  message?: string;
}

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<ReportMeta | null>(null);
  const [report, setReport] = useState<ReportData | null>(null);

  const getReport = async () => {
    if (!keycloak?.token) {
      setError('Not authenticated');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setMeta(null);
      setReport(null);

      await keycloak.updateToken(30);

      const response = await fetch(`${process.env.REACT_APP_API_URL}/reports`, {
        headers: { Authorization: `Bearer ${keycloak.token}` },
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Request failed (${response.status})`);
      }

      const info: ReportMeta = await response.json();
      setMeta(info);

      if (info.status === 'ready' && info.url) {
        const cdnResponse = await fetch(info.url);
        if (!cdnResponse.ok) {
          throw new Error(`CDN fetch failed (${cdnResponse.status})`);
        }
        setReport(await cdnResponse.json());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Отчёт о работе протеза</h1>
          <button
            onClick={() => keycloak.logout()}
            className="text-sm text-gray-500 hover:text-gray-800"
          >
            Выйти ({keycloak.tokenParsed?.preferred_username})
          </button>
        </div>

        <button
          onClick={getReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Формирование отчёта...' : 'Получить отчёт'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {meta?.status === 'no_data' && (
          <div className="mt-4 p-4 bg-yellow-100 text-yellow-800 rounded">
            {meta.message}
          </div>
        )}

        {meta?.status === 'ready' && (
          <div className="mt-4 text-sm text-gray-500">
            Источник: {meta.source === 's3' ? 'кеш S3/CDN' : 'OLAP (сформирован и закеширован)'}
            {meta.url && (
              <>
                {' '}
                <a href={meta.url} target="_blank" rel="noreferrer" className="text-blue-500 underline">
                  ссылка на CDN
                </a>
              </>
            )}
          </div>
        )}

        {report && (
          <div className="mt-4 border-t pt-4">
            <h2 className="text-lg font-semibold mb-2">
              {report.full_name} ({report.username})
            </h2>
            <table className="w-full text-sm">
              <tbody>
                <tr><td className="py-1 text-gray-500">Email</td><td className="text-right">{report.email}</td></tr>
                <tr><td className="py-1 text-gray-500">Страна</td><td className="text-right">{report.country}</td></tr>
                <tr><td className="py-1 text-gray-500">Всего сигналов</td><td className="text-right">{report.signals_total}</td></tr>
                <tr><td className="py-1 text-gray-500">Типов протеза</td><td className="text-right">{report.prosthesis_types}</td></tr>
                <tr><td className="py-1 text-gray-500">Средняя амплитуда</td><td className="text-right">{report.avg_signal_amplitude ?? '-'}</td></tr>
                <tr><td className="py-1 text-gray-500">Средняя длительность</td><td className="text-right">{report.avg_signal_duration ?? '-'}</td></tr>
                <tr><td className="py-1 text-gray-500">Период</td><td className="text-right">{report.period_start ?? '-'} ... {report.period_end ?? '-'}</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;
