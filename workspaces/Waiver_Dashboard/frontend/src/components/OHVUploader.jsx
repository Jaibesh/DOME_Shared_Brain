/**
 * OHVUploader.jsx — OHV Permit upload with camera capture
 * 
 * Two input modes:
 *   📷 Take Photo  → Opens rear camera via capture="environment"
 *   📄 Choose File  → Standard file picker for PDFs/images
 * 
 * Mobile-first: camera capture is the primary action on phones.
 */

import { useState, useRef } from 'react';
import { Camera, FileUp, CheckCircle, AlertCircle } from 'lucide-react';
import axios from 'axios';

export default function OHVUploader({ twConfirmation, initialUploaded = false, onUploadComplete }) {
  const [uploaded, setUploaded] = useState(initialUploaded);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);

  const cameraRef = useRef(null);
  const fileRef = useRef(null);

  const handleFile = async (file) => {
    if (!file) return;

    // Client-side validation
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['jpg', 'jpeg', 'png', 'pdf'].includes(ext)) {
      setError('Please upload a JPG, PNG, or PDF file.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File too large. Maximum size is 10MB.');
      return;
    }

    setError('');
    setUploading(true);
    setProgress(10);

    // Generate preview for images
    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = (e) => setPreview(e.target.result);
      reader.readAsDataURL(file);
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      setProgress(30);
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const response = await axios.post(`${baseUrl}/api/portal/${twConfirmation}/ohv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          const p = Math.round((e.loaded / e.total) * 70) + 30;
          setProgress(Math.min(p, 95));
        },
      });

      setProgress(100);
      setUploaded(true);
      setUploading(false);

      if (onUploadComplete) onUploadComplete(response.data);
    } catch (err) {
      setUploading(false);
      setProgress(0);
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
    }
  };

  if (uploaded) {
    return (
      <div className="ohv-uploader uploaded animate-slide-up">
        <CheckCircle size={40} color="var(--status-ready)" />
        <p style={{ color: 'var(--status-ready)', fontWeight: 700, marginTop: 'var(--space-sm)' }}>
          OHV Permit Uploaded ✓
        </p>
        {preview && (
          <img
            src={preview}
            alt="OHV Permit"
            style={{
              maxWidth: '200px',
              maxHeight: '150px',
              borderRadius: 'var(--radius-sm)',
              marginTop: 'var(--space-md)',
              border: '1px solid var(--status-ready)',
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className={`ohv-uploader ${uploading ? 'dragover' : ''}`}>
      <FileUp size={32} color="var(--text-secondary)" />
      <p style={{ color: 'var(--text-primary)', fontWeight: 600, marginTop: 'var(--space-sm)' }}>
        Upload Your OHV Permit
      </p>
      <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
        Accepted: JPG, PNG, PDF • Max 10MB
      </p>

      {error && (
        <p style={{ color: 'var(--epic-red)', fontSize: '0.85rem', marginTop: 'var(--space-sm)', display: 'flex', alignItems: 'center', gap: '4px', justifyContent: 'center' }}>
          <AlertCircle size={14} /> {error}
        </p>
      )}

      <div className="ohv-upload-actions">
        <button
          className="btn btn-primary"
          onClick={() => cameraRef.current?.click()}
          disabled={uploading}
        >
          <Camera size={18} />
          Take Photo
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          <FileUp size={18} />
          Choose File
        </button>
      </div>

      {/* Hidden file inputs */}
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: 'none' }}
        onChange={(e) => handleFile(e.target.files[0])}
      />
      <input
        ref={fileRef}
        type="file"
        accept=".jpg,.jpeg,.png,.pdf"
        style={{ display: 'none' }}
        onChange={(e) => handleFile(e.target.files[0])}
      />

      {uploading && (
        <div className="ohv-progress">
          <div className="ohv-progress-bar" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}
