/**
 * IndexedDB storage helper for persisting large report states (images, descriptions, etc.)
 * Provides a much larger quota than localStorage.
 */
const ReportStorage = (function() {
    const DB_NAME = 'RoadDamageMonitoringDB';
    const DB_VERSION = 1;
    const STORE_NAME = 'resolved_reports';

    let dbPromise = null;

    /**
     * Initializes the IndexedDB
     */
    function initDB() {
        if (dbPromise) return dbPromise;

        dbPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: 'id' });
                }
            };

            request.onsuccess = (event) => {
                resolve(event.target.result);
            };

            request.onerror = (event) => {
                console.error("IndexedDB error:", event.target.error);
                reject(event.target.error);
            };
        });

        return dbPromise;
    }

    /**
     * Saves a report state to IndexedDB
     * @param {string} reportId 
     * @param {Object} data 
     */
    async function saveReportState(reportId, data) {
        try {
            const db = await initDB();
            return new Promise((resolve, reject) => {
                const transaction = db.transaction([STORE_NAME], 'readwrite');
                const store = transaction.objectStore(STORE_NAME);
                
                const record = {
                    id: reportId,
                    data: data,
                    updatedAt: new Date().toISOString()
                };

                const request = store.put(record);

                request.onsuccess = () => resolve(true);
                request.onerror = (event) => {
                    console.error("Save error:", event.target.error);
                    reject(event.target.error);
                };
            });
        } catch (error) {
            console.error("IndexedDB Save Failed", error);
            throw error;
        }
    }

    /**
     * Retrieves a report state from IndexedDB
     * @param {string} reportId 
     */
    async function getReportState(reportId) {
        try {
            const db = await initDB();
            return new Promise((resolve, reject) => {
                const transaction = db.transaction([STORE_NAME], 'readonly');
                const store = transaction.objectStore(STORE_NAME);
                const request = store.get(reportId);

                request.onsuccess = (event) => {
                    const result = event.target.result;
                    resolve(result ? result.data : null);
                };
                
                request.onerror = (event) => {
                    console.error("Get error:", event.target.error);
                    reject(event.target.error);
                };
            });
        } catch (error) {
            console.error("IndexedDB Get Failed", error);
            return null;
        }
    }

    // Public API
    return {
        save: saveReportState,
        get: getReportState
    };
})();
