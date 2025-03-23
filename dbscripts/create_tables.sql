CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE -- e.g., "URS_System_A"
);

CREATE TABLE source_files (
    id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL, -- e.g., "system_a_urs_v1"
    file_type TEXT NOT NULL CHECK (file_type IN ('docx', 'pdf', 'other')), -- e.g., "docx"
    UNIQUE (document_id, file_name)
);

CREATE TABLE batch_runs (
    id SERIAL PRIMARY KEY,
    run_number INT NOT NULL UNIQUE, -- e.g., 1, 2, 3
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    processed_files INT DEFAULT 0 -- Tracks number of files processed in this run
);



CREATE TABLE source_file_runs (
    id SERIAL PRIMARY KEY,
    source_file_id INT NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
    batch_run_id INT NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
    author TEXT, -- Extracted during batch (e.g., "John Doe")
    created_dt DATE, -- Extracted during batch (e.g., "2023-01-15")
    last_modified_dt DATE, -- Extracted during batch (e.g., "2023-02-10")
    number_pages INT CHECK (number_pages > 0), -- Extracted during batch (e.g., 25)
    UNIQUE (source_file_id, batch_run_id) -- Ensures one entry per file per run
);

CREATE TABLE sections (
    id SERIAL PRIMARY KEY,
    section_name TEXT NOT NULL UNIQUE -- e.g., "Introduction"
);

CREATE TABLE source_file_run_sections (
    source_file_run_id INT NOT NULL REFERENCES source_file_runs(id) ON DELETE CASCADE,
    section_id INT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    PRIMARY KEY (source_file_run_id, section_id)
);

CREATE TABLE content_blocks (
    id SERIAL PRIMARY KEY,
    source_file_run_id INT NOT NULL REFERENCES source_file_runs(id) ON DELETE CASCADE,
    section_id INT REFERENCES sections(id) ON DELETE SET NULL, -- Nullable if section is unknown
    block_number INT NOT NULL, -- e.g., 1, 2, 3 within the file for this run
    content_type TEXT CHECK (content_type IN ('text', 'image', 'table', 'figure', 'title', 'list')), -- Extracted content type
    content TEXT, -- Extracted content
    coord_x1 INT, -- Bounding box
    coord_y1 INT,
    coord_x2 INT,
    coord_y2 INT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    faiss_index_id INT, -- Reference to FAISS index
    UNIQUE (source_file_run_id, block_number) -- Unique per file run
);

CREATE TABLE skipped_block_items (
    id SERIAL PRIMARY KEY,
    batch_run_id INT NOT NULL REFERENCES batch_runs(id) ON DELETE CASCADE,
    parent_block_type VARCHAR(20) NOT NULL,
    skipped_block_type VARCHAR(20) NOT NULL,
    section_name VARCHAR(255),
    parent_block_content VARCHAR(1000),
    skipped_block_content VARCHAR(1000),
    parent_block_coordinates INTEGER[],
    skipped_block_coordinates INTEGER[],
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);