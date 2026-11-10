/**
 * PDF Text Extractor using pdfjs-dist
 * Extracts page-by-page text, page count, and detects whether OCR is required.
 */
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';
import fs from 'fs';
import path from 'path';
import url from 'url';

async function extractPdf(pdfPath) {
    try {
        if (!fs.existsSync(pdfPath)) {
            console.log(JSON.stringify({
                status: 'Error',
                message: `File not found: ${pdfPath}`,
                pageCount: 0,
                fullText: '',
                pages: []
            }));
            process.exit(0);
        }

        const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
        const data = new Uint8Array(fs.readFileSync(pdfPath));
        const cmapUrl = url.pathToFileURL(path.resolve(__dirname, 'node_modules/pdfjs-dist/cmaps')).href + '/';
        const fontUrl = url.pathToFileURL(path.resolve(__dirname, 'node_modules/pdfjs-dist/standard_fonts')).href + '/';

        const loadingTask = pdfjsLib.getDocument({
            data,
            cMapUrl: cmapUrl,
            cMapPacked: true,
            standardFontDataUrl: fontUrl
        });

        const doc = await loadingTask.promise;
        const pageCount = doc.numPages;
        const pages = [];
        let totalTextLength = 0;

        for (let i = 1; i <= pageCount; i++) {
            const page = await doc.getPage(i);
            const content = await page.getTextContent();
            
            // Build page text while strictly preserving line breaks and vertical positioning
            let pageText = '';
            let lastY = null;

            for (const item of content.items) {
                if (!item || !item.str) continue;

                const currentY = (item.transform && item.transform.length >= 6) ? item.transform[5] : null;

                if (lastY !== null && currentY !== null && Math.abs(currentY - lastY) > 5) {
                    pageText += '\n';
                } else if (item.hasEOL) {
                    pageText += '\n';
                } else if (pageText.length > 0 && !pageText.endsWith('\n') && !pageText.endsWith(' ') && !item.str.startsWith(' ')) {
                    pageText += ' ';
                }

                pageText += item.str;
                lastY = currentY;
            }

            pageText = pageText.replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n\n').trim();
            totalTextLength += pageText.length;

            pages.push({
                pageNumber: i,
                text: pageText
            });
        }

        // Check if PDF has embedded digital text or requires OCR
        if (totalTextLength < 15) {
            console.log(JSON.stringify({
                status: 'OCR Required',
                message: 'This PDF appears to be a scanned image or handwritten document with no embedded text layer. OCR (Optical Character Recognition) is required.',
                pageCount: pageCount,
                fullText: '',
                pages: pages
            }));
        } else {
            const formattedFullText = pages
                .filter(p => p.text.length > 0)
                .map(p => `[Page ${p.pageNumber}]\n${p.text}`)
                .join('\n\n');

            console.log(JSON.stringify({
                status: 'Success',
                message: 'Text successfully extracted using pdfjs-dist.',
                pageCount: pageCount,
                fullText: formattedFullText,
                pages: pages
            }));
        }
    } catch (err) {
        console.log(JSON.stringify({
            status: 'Error',
            message: `Extraction failed: ${err.message}`,
            pageCount: 0,
            fullText: '',
            pages: []
        }));
    }
}

const targetPath = process.argv[2];
if (!targetPath) {
    console.log(JSON.stringify({
        status: 'Error',
        message: 'No PDF file path provided.',
        pageCount: 0,
        fullText: '',
        pages: []
    }));
    process.exit(1);
}

extractPdf(targetPath);
