<html> 
	<head> 
    <meta charset="utf-8">
		<title>BEN - The open source bridge engine</title> 
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
        <link rel="stylesheet" href="/app/style.css">
	</head> 
    <script type="text/javascript">
        function copyToClipboard(idx) {
        const bbaText = document.getElementById('bbaText'+idx);
        const text = bbaText.textContent;

        const el = document.createElement('textarea');
        el.value = text;
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        document.body.removeChild(el);

        // You can add a message or any other functionality after copying
        alert('Copied to clipboard: ' + text);
        }
    </script>
<body> 

<center><h1>Play with BEN</a></h1></center>

<div class="container">
  <h2>Play this deal: </h2>

  <div class="content">
    <div class="border">
    <form id="form1">
        <label for="board">Board:</label>
        <input type="input" id="board" name="board"><br>
        <label for="dealer">Dealer:</label>
        <select id="dealer" name="dealer">
            <option value="N">North</option>
            <option value="S">South</option>
            <option value="E">East</option>
            <option value="W">West</option>
        </select><br>
        <label for="vulnerable">Vulnerability:</label>
        <select id="vulnerable" name="vulnerable">
            <option value="None">None</option>
            <option value="NS">NS</option>
            <option value="EW">EW</option>
            <option value="Both">Both</option>
        </select><br>
        <label for="deal">Text:</label>
        <textarea id="deal" name="dealtext" cols="40"></textarea><br>
        <button type="submit" class="submit-button" data-form="form1">Play from text</button>    
    </form>
    </div>
    <br>
    <div class="border">
    <form id="form2">
        <label for="deal">PBN:</label>
        <textarea id="deal" name="dealpbn" cols="40"  rows="10"></textarea><br>
        <button type="submit" class="submit-button" data-form="form2">Play from PBN</button>    
    </form>
    </div>
    <br>
    <div class="border">
    <form id="form3">
        <label for="deal">LIN:</label>
        <textarea id="deallin" name="deallin" cols="40" rows="3"></textarea><br>
        <button type="submit" class="submit-button" data-form="form3">Play from LIN</button>    
    </form>
    </div>
    <br>
    <div class="border">
    <form id="form4">
        <label for="deal">BBA:</label>
        <textarea id="dealbba" name="dealbba" cols="40"></textarea><br>
        <button type="submit" class="submit-button" data-form="form4">Play from BBA</button>    
    </form>
    </div>
    <br>
    <div class="border">
    <form id="form5">
        <label for="board">Board:</label>
        <input type="input" id="board" name="board"><br>
        <button type="submit" class="submit-button" data-form="form5">Play random</button>    
    </form>
    </div>
</div>
</div>

<div class="container">
  <h2>Seatings</h2>

  <div class="content">
    Controlled by human: <br>
    <input type="checkbox" id="N" data-default="false"><label for="N">North</label>
    <input type="checkbox" id="E" data-default="false"><label for="E">East</label>
    <input type="checkbox" id="S" data-default="true"><label for="S">South</label>
    <input type="checkbox" id="W" data-default="false"><label for="W">West</label><br>
    Other options: <br>
    <input type="checkbox" id="H" data-default="true"><label for="H">Human declares</label>
    <input type="checkbox" id="A" data-default="true"><label for="A">Autocomplete trick after 5 sec</label>

  </div>
</div>
<div class="container">
  <h2>Previous played deals</h2>

  <div class="content">
<ul>
% for index, deal in enumerate(deals):
    <li>
        <span>{{deal['board_no_index']}}  <a href="/app/viz.html?deal={{deal['deal_id']}}{{deal['board_no_ref']}}">{{deal['contract']}}{{deal.get('trick_winners_count', '')}}</a></span>&nbsp;&nbsp;
        <span><a href="{{deal['delete_url']}}">delete</a></span><br>
        <span class="bba">BBA=<span id="bbaText{{index}}">{{deal['bba']}}&nbsp;<i class="fas fa-copy" onclick="copyToClipboard({{index}})"></i>
        </span>
        </span>
    </li>
% end
</ul>
</div>
</div>

<script type="text/javascript">

// Get reference to the checkboxes and forms
const checkbox1 = document.getElementById('N');
const checkbox2 = document.getElementById('E');
const checkbox3 = document.getElementById('S');
const checkbox4 = document.getElementById('W');
const checkbox5 = document.getElementById('H');
const checkbox6 = document.getElementById('A');

// Function to save checkbox state in localStorage
function saveCheckboxState(checkboxId, checked) {
    localStorage.setItem(checkboxId, checked);
}

// Function to load checkbox state from localStorage or set default
function loadCheckboxState(checkboxId, defaultChecked) {
    const savedCheckboxState = localStorage.getItem(checkboxId);

    // If no value exists in localStorage, set a default value
    if (savedCheckboxState === null) {
        saveCheckboxState(checkboxId, defaultChecked); // Set default value to false (unchecked)
        return false;
    } else {
        return savedCheckboxState === 'true';
    }
}

// Load checkbox states when the page is loaded
document.addEventListener('DOMContentLoaded', function() {
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');

    checkboxes.forEach(checkbox => {
        const defaultChecked = checkbox.getAttribute('data-default') === 'true';
        checkbox.checked = loadCheckboxState(checkbox.id, defaultChecked);

        checkbox.addEventListener('click', function() {
            saveCheckboxState(checkbox.id, this.checked);
        });
    });
});

const submitButtons = document.querySelectorAll('.submit-button');

// Variable to store the selected form
let selectedForm = null;


// Function to include checkbox values in form submission
function includeCheckboxValues(event) {
    event.preventDefault(); // Prevents the default form submission

    if (selectedForm) {
        const formData = new FormData(selectedForm);
        const checkboxes = [checkbox1, checkbox2, checkbox3, checkbox4, checkbox5, checkbox6];
        checkboxes.forEach(checkbox => {
            if (checkbox.checked) {
                formData.append(checkbox.id, checkbox.value);
            }
        });

        // You can submit the form data using fetch or XMLHttpRequest here
        // For example:
        fetch('/submit', {
             method: 'POST',
             body: formData
        })
        .then(response => {
            if (response.redirected) {
                // If the response indicates a redirect, you can handle it here
                // For example, you can redirect the user to the new location
                window.location.href = response.url;
            }        
        })
        .catch(error => {
            // Handle error
        });
        console.log('Form Data:', formData); // For demonstration purposes
    };
}

// Function to update selectedForm variable based on button click
function updateSelectedForm(event) {
    selectedForm = document.getElementById(this.dataset.form);
}

// Attach the includeCheckboxValues function to form submit events
submitButtons.forEach(button => {
    button.addEventListener('click', updateSelectedForm);
    button.addEventListener('click', includeCheckboxValues);
});

</script>
</body> 
</html> 
