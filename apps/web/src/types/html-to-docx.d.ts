declare module 'html-to-docx' {
  interface HTMLtoDOCXOptions {
    table?: {
      row?: {
        cantSplit?: boolean;
      };
    };
    footer?: boolean;
    pageNumber?: boolean;
    font?: string;
    fontSize?: number;
    margins?: {
      top?: number;
      right?: number;
      bottom?: number;
      left?: number;
    };
    lineNumber?: boolean;
  }

  function HTMLtoDOCX(
    html: string,
    headerHTMLString?: string | null,
    options?: HTMLtoDOCXOptions,
    phpBuffer?: Buffer
  ): Promise<Buffer>;

  export = HTMLtoDOCX;
}
