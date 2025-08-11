let currentFeatureId = null;
const map = L.map('map', { zoomControl: false }).setView([-40.9006, 174.8860], 5);

const aerial = L.tileLayer(
    'https://basemaps.linz.govt.nz/v1/tiles/aerial/WebMercatorQuad/{z}/{x}/{y}.webp?api=c01jz2g4ry48rv88t3j4bgm1qxc',
    {
        maxZoom: 15,
        attribution: '© LINZ CC BY 4.0'
    }
);
const topo = L.tileLayer(
    'https://basemaps.linz.govt.nz/v1/tiles/topo-raster/WebMercatorQuad/{z}/{x}/{y}.webp?api=c01jz2g4ry48rv88t3j4bgm1qxc',
    {
        maxZoom: 15,
        attribution: '© LINZ CC BY 4.0'
    }
);

const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
});

const baseMaps = {
    "Topo50": topo,
    "Aerial": aerial,
    "OpenStreetMap": osm,
};

topo.addTo(map); // default layer

L.control.layers(baseMaps).addTo(map);

L.control.zoom({
    position: 'bottomright'
}).addTo(map);

const drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

const drawControl = new L.Control.Draw({
    draw: {
        polygon: true,
        polyline: true,
        rectangle: false,
        circle: false,
        marker: true,
        circlemarker: false
    },
    edit: {
        featureGroup: drawnItems // A layer group to store drawn features
    }
});
map.addControl(drawControl);

let isAddingAltGeometry = false;

$(document).on('click', '#addGeometry', function() {
    if (!currentFeatureId) {
        alert("Please select a feature first.");
        return;
    }

    isAddingAltGeometry = true;
    alert("Draw a new geometry on the map for the selected feature.");
});

map.on('draw:created', function (e) {
    const layer = e.layer;
    const geojson = layer.toGeoJSON();

    drawnItems.addLayer(layer);

    if (isAddingAltGeometry && currentFeatureId) {
        // Send directly as alternative geometry
        const userName = prompt("Enter your name to submit alternative geometry:");
        if (!userName) {
            alert("Submission cancelled.");
            drawnItems.removeLayer(layer);
            isAddingAltGeometry = false;
            return;
        }

        $.ajax({
            url: "/add_alternative_geometry",
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify({
                feature_name_id: currentFeatureId,
                geometry: geojson,
                updated_by: userName
            }),
            success: function(response) {
                alert("Alternative geometry added!");
                drawnItems.removeLayer(layer);
                isAddingAltGeometry = false;
            },
            error: function() {
                alert("Failed to add geometry.");
                drawnItems.removeLayer(layer);
                isAddingAltGeometry = false;
            }
        });
    } else {
        // Normal add feature
        openAddFeatureModal(geojson);
    }
});


let geojsonLayer;

let pendingGeometry = null;

function openAddFeatureModal(geojson) {
    pendingGeometry = geojson;
    $('#addFeatureModal').show();
    $('#addFeatureForm')[0].reset();
}

$('#cancelFeatureButton').on('click', function() {
    $('#addFeatureModal').hide();
    pendingGeometry = null;
    drawnItems.clearLayers();
});

$('#addFeatureForm').on('submit', function(e) {
    e.preventDefault(); // prevent default form submission

    if (!pendingGeometry) {
        alert("No geometry selected.");
        return;
    }

    const formData = $(this).serializeArray();
    const formObj = {};
    formData.forEach(item => {
        formObj[item.name] = item.value;
    });

    // Add geometry
    formObj.geometry = pendingGeometry;
    console.log("Form object:", formObj);

    $.ajax({
        url: "/add_feature",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify(formObj),
        success: function(response) {
            alert("Feature added successfully!");
            $('#addFeatureModal').hide();
            pendingGeometry = null;
            drawnItems.clearLayers();
        },
        error: function() {
            alert("Failed to add feature.");
            drawnItems.clearLayers();
        }
    });
});
$('#search_bar').autocomplete({
    source: function (req, res) {
        $.post('/api/search', {search_term: req.term}, function (out) {
            const data = (out.data || out).map(item => ({
                label: item.featurename,
                value: item.featurename,
                id: item.id
            }));
            res(data);
        });
    },
    minLength: 3,
    select: function(event, ui) {
        const featurename_id = ui.item.id;
        const encodedURI = encodeURI(ui.item.value);
        const featureName = encodedURI.replace(/%20/g, ' ');
        displayGeometries(featureName);
    }
});

function displayGeometries(featureName) {
    if (geojsonLayer) {
        map.removeLayer(geojsonLayer);
    }
    $.post('/api/get_geometries', {feature_name: featureName}, function (resp) {
        const rows = resp.data || resp; // backward compatibility
        if (!rows || rows.length === 0) {
            alert('No geometries found.');
            return;
        }
        const features = rows.map(item => ({
            type: 'Feature',
            properties: {
                name: featureName,
                geometryType: item.type,
                featurenameId: item.featurename_id,
                source: item.source
            },
            geometry: JSON.parse(item.geometry)
        }));
        geojsonLayer = L.geoJSON(features, {
            onEachFeature: (feature, layer) => {
                layer.on('click', () => showFeatureDetails(feature.properties));
            }
        }).addTo(map);
        try {
            map.fitBounds(geojsonLayer.getBounds());
            map.setZoom(30);
        } catch (_) {
        }
        showFeatureDetails(features[0].properties);
    }).fail(() => alert('Searching Error!'));
}

function showFeatureDetails(properties) {
    const container = document.getElementById('feature_details');
    container.innerHTML = '<h2>Feature Details</h2>';
    console.log("**********************************");
    console.log("Properties:", properties);
    const name = properties.name;
    const currentSource = properties.source;

    container.innerHTML += `<h3><strong>${name}</strong></h3>`;

    // Initially render the placeholder for the panel and dropdown
    container.innerHTML += `
        <div id="sourceSelectorContainer"></div>
        <hr>
        <div id="sourceDetailsPanel"><p><em>Loading details...</em></p></div>
    `;


    // Render the dropdown dynamically into the correct container
    document.getElementById('sourceSelectorContainer').innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
            <label for="sourceDropdown" style="white-space: nowrap;"><strong>Source:</strong></label>
            <select id="sourceDropdown" style="width: 150px;">
                <option value="NZGB" ${currentSource === 'NZGB' ? 'selected' : ''}>NZGB</option>
                <option value="Geonames" ${currentSource === 'Geonames' ? 'selected' : ''}>GeoNames</option>
                <option value="OSM" ${currentSource === 'OSM' ? 'selected' : ''}>OpenStreetMap</option>
            </select>
            <button id="addName">Add alternative name</button>
            <button id="addGeometry">Add alternative geometry</button>
        </div>
    `;

    // Fetch metadata for the initial source
    fetchFeatureDetails(properties.featurenameId, name, currentSource);

    // Now safely bind change event
    const sourceDropdown = document.getElementById('sourceDropdown');
    sourceDropdown.addEventListener('change', function () {
        const selectedSource = this.value;
        console.log("Selected source:", selectedSource);
        fetchFeatureDetails(properties.featurenameId, name, selectedSource);
    });
}

function fetchFeatureDetails(featureNameId, featureName, source) {
    const panel = document.getElementById('sourceDetailsPanel');
    panel.innerHTML = `<p><em>Loading details from ${source}...</em></p>`;

    $.post('api/get_feature_metadata', {
        feature_name_id: featureNameId,
        feature_name: featureName,
        source: source
    }, function(metadata) {
        panel.innerHTML = ''; // clear old content

        if (!metadata || Object.keys(metadata).length === 0) {
            panel.innerHTML = `<p><em>No details available from ${source}.</em></p>`;
            return;
        }

        if (metadata.maori_name) {
            panel.innerHTML += `<p><strong>Māori Name:</strong> ${metadata.maori_name}</p>`;
        }

        panel.innerHTML += `<p><strong>Feature Type:</strong> ${metadata.feature_type || '—'}</p>`;
        panel.innerHTML += `<p><strong>Feature Description:</strong> ${metadata.feature_description || '—'}</p>`;

        const formattedWhakapapa = metadata.whakapapa
            ? metadata.whakapapa.replace(/\n/g, "<br>")
            : null;
        const formattedAncestor = metadata.ancestor
            ? metadata.ancestor.replace(/\n/g, "<br>")
            : null;

        if (formattedWhakapapa) {
            panel.innerHTML += `<p><strong>Origin Story:</strong> ${formattedWhakapapa}</p>`;
        } else {
            currentFeatureId = featureNameId;
            panel.innerHTML += `
                <p><strong>Place Kōrero (Origin):</strong> Not available</p>
                <button id="addWhakapapaButton">Add Kōrero</button>
            `;
        }

        if (formattedAncestor) {
            panel.innerHTML += `<p><strong>Tipuna (Ancestor):</strong> ${formattedAncestor}</p>`;
        } else {
            currentFeatureId = featureNameId;
            panel.innerHTML += `
                <p><strong>Tipuna (Ancestor):</strong> Not available</p>
                <button id="addAncestorButton">Add Tipuna</button>
            `;
        }

        if (metadata.other_names) {
            panel.innerHTML += `<p><strong>Other Names:</strong> ${metadata.other_names}</p>`;
        }
    }).fail(function() {
        panel.innerHTML = `<p><em>Failed to load details from ${source}.</em></p>`;
    });
}


/*document.getElementById('run_query_btn').addEventListener('click', function () {
    const sql = document.getElementById('sql_input').value;

    $.post('/run_query', { sql }, function (result) {
        const output = result.data || result.error || 'No result';
        document.getElementById('query_result').textContent = JSON.stringify(output, null, 2);
    }).fail(function () {
        document.getElementById('query_result').textContent = 'Query failed.';
    });
  });*/
$(document).on('click', '#addName', function() {
    $('#altNameModal').show();
    $('#altNameInput').focus();
});

$('#cancelAltNameButton').on('click', function() {
    $('#altNameModal').hide();
    $('#altNameInput').val('');
    $('#altNameUserInput').val('');
});

$('#saveAltNameButton').on('click', function() {
    const altName = $('#altNameInput').val().trim();
    const username = $('#altNameUserInput').val().trim();

    if (!altName || !username) {
        alert("Please provide both the alternative name and your name.");
        return;
    }

    $.post('api/add_alternative_name', {
        feature_name_id: currentFeatureId,
        alternative_name: altName,
        updated_by: username
    }, function(response) {
        alert("Alternative name added successfully!");
        $('#altNameModal').hide();
        $('#altNameInput').val('');
        $('#altNameUserInput').val('');
    }).fail(function() {
        alert("Failed to add alternative name.");
    });
});
$(document).on('click', '#addWhakapapaButton', function() {
    $('#whakapapaModal').show();
    $('#whakapapaInput').focus();
});
$('#cancelWhakapapaButton').on('click', function() {
    $('#whakapapaModal').hide();
});
$('#saveWhakapapaButton').on('click', function() {
    const newWhakapapa = $('#whakapapaInput').val().trim();
    const username = $('#usernameInput').val().trim();

    if (newWhakapapa.length === 0) {
        alert("Please enter whakapapa text.");
        return;
    }
    if (username.length === 0) {
        alert("Please enter your name.");
        return;
    }

    $.post('api/add_whakapapa', {
        feature_name_id: currentFeatureId,
        whakapapa_text: newWhakapapa,
        updated_by: username
    }, function(response) {
        alert("Whakapapa added successfully!");
        $('#whakapapaModal').hide();
        $('#whakapapaInput').val("");   // Clear textarea
        $('#usernameInput').val("");    // Clear username field
    }).fail(function() {
        alert("Failed to add whakapapa.");
    });
});
$(document).on('click', '#addAncestorButton', function() {
    $('#ancestorModal').show();
    $('#ancestorInput').focus();
});
$('#cancelAncestorButton').on('click', function() {
    $('#ancestorModal').hide();
});
$('#saveAncestorButton').on('click', function() {
    const ancestorText = $('#ancestorInput').val().trim();
    const username = $('#usernameInput').val().trim();

    if (ancestorText.length === 0) {
        alert("Please enter the name of the ancestor related to this place.");
        return;
    }
    if (username.length === 0) {
        alert("Please enter your name.");
        return;
    }

    $.post('api/add_ancestor', {
        feature_name_id: currentFeatureId,
        ancestor_text: ancestorText,
        updated_by: username
    }, function(response) {
        alert("Tipuna/Ancestor(s) added successfully!");
        $('#ancestorModal').hide();
        $('#ancestorInput').val("");   // Clear textarea
        $('#usernameInput').val("");    // Clear username field
    }).fail(function() {
        alert("Failed to add Tipuna/Ancestor(s).");
    });
});
