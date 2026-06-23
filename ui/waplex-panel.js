/**
 * WaplexPanel — self-contained React component for managing a WAPlex WhatsApp session.
 *
 * Props:
 *   apiGet(path)           -> Promise<{data}>   e.g. (path) => axios.get(path)
 *   apiPost(path, body)    -> Promise<{data}>
 *   whatsappNumber: string — configured WA number shown in the idle state
 *   showToast(msg, type)   -> void  (type: 'success' | 'error') — optional
 *   Icon: component        — optional; ({ name, size }) -> JSX. Falls back to plain text.
 *   basePath: string       — optional; prefix for all session API routes.
 *                            Default: '/api/whatsapp/session'
 *   onError: function      — optional; called with the raw error on any fetch failure.
 *
 * Backend routes required (mount whatsapp_session router in your FastAPI app):
 *   GET  <basePath>/status
 *   GET  <basePath>/qr
 *   POST <basePath>/start        body: { number }
 *   POST <basePath>/disconnect
 *
 * Usage (vanilla React via CDN):
 *   <script src="waplex-panel.js"></script>
 *   ReactDOM.render(
 *     React.createElement(window.WaplexPanel, { apiGet, apiPost, whatsappNumber, showToast }),
 *     document.getElementById('wa-panel')
 *   );
 */
(function () {
    const S = {
        card: {
            background: 'var(--bg-card, #fff)',
            border: '1px solid var(--border, #e5e7eb)',
            borderRadius: '16px',
            overflow: 'hidden',
            boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        },
        header: {
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--border, #e5e7eb)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
        },
        body: {
            padding: '1.5rem',
            minHeight: '180px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
        },
        title: { margin: 0, fontSize: '1rem', fontWeight: 600 },
        subtitle: { margin: '0.25rem 0 0', fontSize: '0.8125rem', color: 'var(--text-muted, #6b7280)' },
        badge: (status) => ({
            padding: '0.3rem 0.65rem',
            borderRadius: '9999px',
            fontSize: '0.7rem',
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            background: status === 'CONNECTED' ? '#dcfce7' : status === 'CONNECTING' ? '#fef9c3' : status === 'DISCONNECTED' ? '#fee2e2' : '#f3f4f6',
            color: status === 'CONNECTED' ? '#166534' : status === 'CONNECTING' ? '#854d0e' : status === 'DISCONNECTED' ? '#991b1b' : '#374151',
        }),
        spinner: {
            width: '32px', height: '32px',
            border: '3px solid var(--border, #e5e7eb)',
            borderTop: '3px solid var(--primary, #0d9488)',
            borderRadius: '50%',
            animation: 'waplex-spin 0.8s linear infinite',
            margin: '0 auto 0.75rem',
        },
        btnPrimary: {
            width: '100%', padding: '0.65rem 1rem',
            background: 'var(--primary, #0d9488)', color: '#fff',
            border: 'none', borderRadius: '10px', fontWeight: 600,
            fontSize: '0.875rem', cursor: 'pointer',
        },
        btnSecondary: {
            flex: 1, padding: '0.6rem 1rem',
            background: 'transparent',
            border: '1px solid var(--border, #e5e7eb)',
            borderRadius: '10px', fontWeight: 500,
            fontSize: '0.875rem', cursor: 'pointer',
            color: 'var(--text, #111)',
        },
        btnDanger: {
            flex: 1, padding: '0.6rem 1rem',
            background: 'transparent',
            border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: '10px', fontWeight: 500,
            fontSize: '0.875rem', cursor: 'pointer',
            color: '#ef4444',
        },
        center: { textAlign: 'center', width: '100%' },
        muted: { fontSize: '0.8125rem', color: 'var(--text-muted, #6b7280)' },
        pairingBox: {
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: '0.25rem', padding: '1rem',
            background: 'rgba(0,0,0,0.03)',
            borderRadius: '12px', border: '1px dashed var(--border, #e5e7eb)',
            width: '100%', maxWidth: '280px',
        },
        pairingCode: {
            fontSize: '1.75rem', fontWeight: 700,
            letterSpacing: '3px', color: 'var(--primary, #0d9488)',
        },
        instructionList: {
            paddingLeft: '1.2rem', margin: 0,
            display: 'flex', flexDirection: 'column', gap: '0.25rem',
            fontSize: '0.8rem', color: 'var(--text-muted, #6b7280)',
        },
        numberRow: {
            padding: '0.65rem 0.875rem',
            background: 'var(--bg-main, #f9fafb)',
            borderRadius: '8px',
            border: '1px solid var(--border, #e5e7eb)',
            fontSize: '0.8125rem',
            marginBottom: '1.25rem',
        },
    };

    // Inject keyframe once
    if (!document.getElementById('waplex-style')) {
        const st = document.createElement('style');
        st.id = 'waplex-style';
        st.textContent = '@keyframes waplex-spin { to { transform: rotate(360deg); } }';
        document.head.appendChild(st);
    }

    const DefaultIcon = ({ name }) => {
        const labels = { 'check-circle': '✓', copy: '⎘', 'message-circle': '💬' };
        return React.createElement('span', null, labels[name] || '');
    };

    const WaplexPanel = ({ apiGet, apiPost, whatsappNumber, showToast, Icon,
                           basePath = '/api/whatsapp/session', onError }) => {
        const { useState, useEffect, useRef } = React;
        const toast = showToast || ((m, t) => t === 'error' ? console.error('[WaplexPanel]', m) : console.log('[WaplexPanel]', m));
        const Ico = Icon || DefaultIcon;

        // Keep latest callbacks in refs so the poll closure always calls the current
        // function without needing to be in the useEffect dep array — prevents the
        // interval from restarting every time the parent re-renders with a new inline fn.
        const apiGetRef = useRef(apiGet);
        const apiPostRef = useRef(apiPost);
        useEffect(() => { apiGetRef.current = apiGet; });
        useEffect(() => { apiPostRef.current = apiPost; });

        const [waStatus, setWaStatus] = useState({ status: 'NOT_INITIALIZED', connected: false });
        const [waPairingCode, setWaPairingCode] = useState(null);
        const [waLoading, setWaLoading] = useState(false);
        const [confirmDisconnect, setConfirmDisconnect] = useState(false);
        const waLoadingRef = useRef(false);
        const confirmTimer = useRef(null);

        useEffect(() => { waLoadingRef.current = waLoading; }, [waLoading]);

        // Cleanup confirm timer on unmount
        useEffect(() => () => clearTimeout(confirmTimer.current), []);

        const p = (suffix) => `${basePath}${suffix}`;

        useEffect(() => {
            let active = true;
            let poll = null;

            const fetchQr = async () => {
                try {
                    const res = await apiGetRef.current(p('/qr'));
                    if (!active) return;
                    const qr = res.data.qr;
                    setWaPairingCode(qr && typeof qr === 'object' ? (qr.pairingCode || null) : null);
                } catch (e) {
                    if (!active) return;
                    if (onError) onError(e);
                    else console.error('[WaplexPanel] qr error', e);
                }
            };

            const fetchStatus = async () => {
                // Don't overwrite status mid user-action to avoid flicker
                if (waLoadingRef.current) return;
                try {
                    const res = await apiGetRef.current(p('/status'));
                    if (!active) return;
                    setWaStatus(res.data);
                    if (res.data.status === 'DISCONNECTED' || res.data.status === 'CONNECTING') {
                        fetchQr();
                    } else {
                        setWaPairingCode(null);
                    }
                } catch (e) {
                    if (!active) return;
                    if (onError) onError(e);
                    else console.error('[WaplexPanel] status error', e);
                }
            };

            fetchStatus();
            poll = setInterval(fetchStatus, 5000);
            return () => { active = false; clearInterval(poll); };
        }, []); // eslint-disable-line react-hooks/exhaustive-deps

        const handleStart = async () => {
            if (!whatsappNumber) {
                toast('Configure a WhatsApp number first.', 'error');
                return;
            }
            setConfirmDisconnect(false);
            clearTimeout(confirmTimer.current);
            setWaLoading(true);
            try {
                await apiPostRef.current(p('/start'), { number: whatsappNumber });
                toast('WhatsApp session starting...');
                const r = await apiGetRef.current(p('/status'));
                setWaStatus(r.data);
            } catch (e) {
                const msg = e?.response?.data?.detail || 'Failed to start WhatsApp session';
                toast(msg, 'error');
                if (onError) onError(e);
            } finally {
                setWaLoading(false);
            }
        };

        const handleStop = async () => {
            // Two-tap confirmation — avoids window.confirm which is blocked in cross-origin iframes
            if (!confirmDisconnect) {
                setConfirmDisconnect(true);
                clearTimeout(confirmTimer.current);
                confirmTimer.current = setTimeout(() => setConfirmDisconnect(false), 3000);
                return;
            }
            clearTimeout(confirmTimer.current);
            setConfirmDisconnect(false);
            setWaLoading(true);
            try {
                await apiPostRef.current(p('/disconnect'), {});
                toast('WhatsApp session disconnected');
                setWaStatus({ status: 'NOT_INITIALIZED', connected: false });
                setWaPairingCode(null);
            } catch (e) {
                const msg = e?.response?.data?.detail || 'Failed to disconnect WhatsApp session';
                toast(msg, 'error');
                if (onError) onError(e);
            } finally {
                setWaLoading(false);
            }
        };

        const status = waStatus.status || 'UNKNOWN';

        return React.createElement('div', { style: S.card },
            // Header
            React.createElement('div', { style: S.header },
                React.createElement('div', null,
                    React.createElement('h3', { style: S.title }, 'WhatsApp Session'),
                    React.createElement('p', { style: S.subtitle }, 'Manage your WhatsApp connection'),
                ),
                React.createElement('span', { style: S.badge(status) }, status.replace('_', ' ')),
            ),

            // Body
            React.createElement('div', { style: S.body },

                // Loading spinner
                waLoading && React.createElement('div', { style: S.center },
                    React.createElement('div', { style: S.spinner }),
                    React.createElement('span', { style: S.muted }, 'Processing...'),
                ),

                // CONNECTED state
                !waLoading && status === 'CONNECTED' && React.createElement('div', { style: S.center },
                    React.createElement('div', { style: { display: 'inline-flex', background: 'rgba(22,163,74,0.1)', color: '#16a34a', padding: '0.75rem', borderRadius: '50%', marginBottom: '0.75rem' } },
                        React.createElement(Ico, { name: 'check-circle', size: 28 }),
                    ),
                    React.createElement('p', { style: { fontWeight: 600, marginBottom: '0.25rem' } }, 'WhatsApp Linked Successfully'),
                    React.createElement('p', { style: { ...S.muted, marginBottom: '1.25rem' } }, 'Session is active and ready to deliver notifications.'),
                    React.createElement('button', {
                        style: { ...S.btnDanger, width: '100%', flex: 'unset' },
                        onClick: handleStop,
                        disabled: waLoading,
                    }, confirmDisconnect ? 'Tap again to confirm disconnect' : 'Disconnect WhatsApp'),
                ),

                // CONNECTING / DISCONNECTED-with-pairing-code state
                !waLoading && (status === 'CONNECTING' || (status === 'DISCONNECTED' && waPairingCode)) &&
                React.createElement('div', { style: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.75rem', width: '100%' } },
                    waPairingCode
                        ? React.createElement('div', { style: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem', width: '100%' } },
                            React.createElement('div', { style: S.pairingBox },
                                React.createElement('span', { style: { ...S.muted, fontSize: '0.75rem' } }, 'WhatsApp Pairing Code'),
                                React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: '0.75rem' } },
                                    React.createElement('span', { style: S.pairingCode }, waPairingCode),
                                    React.createElement('button', {
                                        style: { background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted, #6b7280)', padding: '4px', display: 'flex', alignItems: 'center' },
                                        title: 'Copy pairing code',
                                        onClick: () => { navigator.clipboard.writeText(waPairingCode); toast('Pairing code copied!'); },
                                    }, React.createElement(Ico, { name: 'copy', size: 18 })),
                                ),
                            ),
                            React.createElement('div', { style: { ...S.muted, width: '100%', maxWidth: '280px', marginTop: '0.5rem' } },
                                React.createElement('p', { style: { fontWeight: 600, marginBottom: '0.25rem', fontSize: '0.8rem' } }, 'How to link your device:'),
                                React.createElement('ol', { style: S.instructionList },
                                    React.createElement('li', null, 'Open WhatsApp on your mobile phone'),
                                    React.createElement('li', null, 'Go to ', React.createElement('strong', null, 'Linked Devices'), ' (Menu or Settings)'),
                                    React.createElement('li', null, 'Tap ', React.createElement('strong', null, 'Link a Device')),
                                    React.createElement('li', null, 'Select ', React.createElement('strong', null, 'Link with phone number instead')),
                                    React.createElement('li', null, 'Enter the 8-character pairing code above'),
                                ),
                            ),
                        )
                        : React.createElement('div', { style: S.center },
                            React.createElement('div', { style: S.spinner }),
                            React.createElement('span', { style: S.muted }, 'Generating Pairing Code...'),
                        ),

                    React.createElement('div', { style: { display: 'flex', gap: '0.5rem', width: '100%', marginTop: '0.5rem' } },
                        React.createElement('button', { style: S.btnSecondary, onClick: handleStart, disabled: waLoading }, 'Regenerate Code'),
                        React.createElement('button', { style: S.btnDanger, onClick: handleStop, disabled: waLoading },
                            confirmDisconnect ? 'Confirm Stop' : 'Stop Session'),
                    ),
                ),

                // Idle / NOT_INITIALIZED state
                !waLoading && status !== 'CONNECTED' && status !== 'CONNECTING' && !(status === 'DISCONNECTED' && waPairingCode) &&
                React.createElement('div', { style: S.center },
                    React.createElement('p', { style: { ...S.muted, marginBottom: '1.25rem' } },
                        'Connect your WhatsApp account to enable automated transactional alerts.',
                    ),
                    React.createElement('div', { style: S.numberRow },
                        React.createElement('span', { style: S.muted }, 'Configured number: '),
                        React.createElement('strong', { style: { color: 'var(--primary, #0d9488)' } }, whatsappNumber || 'Not configured'),
                    ),
                    React.createElement('button', {
                        style: { ...S.btnPrimary, opacity: (!whatsappNumber || waLoading) ? 0.6 : 1, cursor: (!whatsappNumber || waLoading) ? 'not-allowed' : 'pointer' },
                        onClick: handleStart,
                        disabled: waLoading || !whatsappNumber,
                    }, whatsappNumber ? 'Connect WhatsApp' : 'Configure WhatsApp Number First'),
                ),
            ),

            // Attribution notice required by Evolution API license (Apache 2.0 + custom conditions)
            React.createElement('div', {
                style: {
                    padding: '0.5rem 1.5rem',
                    borderTop: '1px solid var(--border, #e5e7eb)',
                    fontSize: '0.7rem',
                    color: 'var(--text-muted, #9ca3af)',
                    textAlign: 'center',
                },
            },
                'Powered by ',
                React.createElement('a', {
                    href: 'https://github.com/EvolutionAPI/evolution-api',
                    target: '_blank',
                    rel: 'noopener noreferrer',
                    style: { color: 'inherit', textDecoration: 'underline' },
                }, 'Evolution API'),
                ' (Apache 2.0)',
            ),
        );
    };

    window.WaplexPanel = WaplexPanel;
})();
